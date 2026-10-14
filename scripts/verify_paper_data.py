"""Check this checkout against prompts and outcomes recorded by the paper's runs.

Zero cost: no provider call is made.  Every check recomputes something from
an episode log with this package and compares it with what the paper's run
recorded at the time:

  episode logs   every acting call's logged prompt digest (system block,
                 including any variant mandate, plus the uninjected user
                 render), and the settled result.
  wire receipts  (clear-goal runs) the SHA-256 of every outbound message
                 list, reconstructed from the log including corrective
                 re-prompts; this covers the variant reminder too.
  v2 campaign    the input_sha256 and state_sha256 of every S1 (target
                 replay), S2 (reader view) and S4 (partner-brief replay)
                 cell.

Usage:
  python scripts/verify_paper_data.py --logs DIR [DIR ...]
  python scripts/verify_paper_data.py --v2-campaign DIR --shuffle-salt HEX

The data directories belong to the study repository and are not shipped
with FORGE.  The script exits non-zero if any comparison fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.core import fold as fold_mod                             # noqa: E402
from forge.grading.scoring import settle                            # noqa: E402
from forge.reader.decision import (                                 # noqa: E402
    build_decision_views, forecast_system_block, state_digest)
from forge.reader.evidence import prompt_digest                     # noqa: E402
from forge.render.render import (                                   # noqa: E402
    append_user_section, render_prompt, render_user, system_block)
from forge.runtime.agents import corrective                         # noqa: E402
from forge.runtime.replay import decision_prompt, load_events       # noqa: E402
from forge.scenarios.bank import load_bank                          # noqa: E402
from forge.variants import extend_scenario, mover_reminder          # noqa: E402
from forge.variants.hidden_priority import partner_brief_line       # noqa: E402

# The five-model clear-goal study added this sentence to corrective
# re-prompts after an empty COMMIT (a study-side shim, not part of FORGE).
FIVE_MODEL_COMMIT_REPAIR = (
    " The slots map cannot be empty. Copy the visible opening-menu "
    "slot IDs and include one allowed value for each slot."
)

_BANKS: dict[str, dict] = {}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def bank_scenario(bank: str, scenario_id: str):
    if bank not in _BANKS:
        _BANKS[bank] = {sc.scenario_id: sc for sc in load_bank(bank)}
    return _BANKS[bank][scenario_id]


def scenario_for_log(meta: dict, events: list):
    """The bank scenario, extended when the log played the extended deadline."""
    base = bank_scenario(meta["bank"] or "v1", meta["scenario_id"])
    last = max((event.tick for event in events), default=0)
    extended = extend_scenario(base)
    if last == extended.params.D:
        return extended
    if last == base.params.D:
        return base
    return None


def wire_messages_by_seat(scenario, events, records, meta, *, five_model: bool):
    """Rebuild every outbound message list ModelAgent sent, per seat."""
    out: dict[str, list[str]] = defaultdict(list)
    current: dict[str, list] = {}
    for record in records:
        if record.get("kind") != "call" or record.get("purpose") != "act":
            continue
        if "raw" not in record:
            continue                 # the post-failure invalid-WAIT marker
        seat, tick = record["seat"], int(record["tick"])
        if int(record.get("attempt", 1)) == 1:
            mandate = meta["seats"][seat].get("mandate", "principal")
            state = fold_mod.state_at(scenario, events, tick)
            prefix = tuple(e for e in events if e.tick < tick)
            user = render_user(state, prefix, seat)
            reminder = mover_reminder(mandate)
            if reminder:
                user = append_user_section(user, reminder)
            current[seat] = [
                {"role": "system",
                 "content": system_block(scenario, mandate).decode("utf-8")},
                {"role": "user", "content": user},
            ]
        messages = current[seat]
        out[seat].append(hashlib.sha256(json.dumps(
            messages, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest())
        error = record.get("error")
        if error:
            msg = (record["raw"].get("choices") or [{}])[0].get("message") or {}
            extra = corrective(msg, error)
            if five_model and "COMMIT needs slots" in error:
                for message in extra:
                    if message.get("role") in {"tool", "user"}:
                        message["content"] = (message.get("content") or "") + FIVE_MODEL_COMMIT_REPAIR
            current[seat] = messages + extra
    return out


def check_log(path: Path, tally: Counter, failures: list, *, five_model: bool) -> None:
    records = read_jsonl(path)
    meta = next((r for r in records if r.get("kind") == "meta"), None)
    if meta is None:
        return
    events = load_events(records)
    scenario = scenario_for_log(meta, events)
    if scenario is None:
        tally["logs_skipped_incomplete_or_nonstandard_deadline"] += 1
        return
    tally["logs"] += 1
    for record in records:
        if record.get("kind") != "call" or record.get("purpose") != "act":
            continue
        if not record.get("digest"):
            continue
        seat, tick = record["seat"], int(record["tick"])
        mandate = meta["seats"][seat].get("mandate", "principal")
        state = fold_mod.state_at(scenario, events, tick)
        prefix = tuple(e for e in events if e.tick < tick)
        _, digest = render_prompt(state, prefix, seat, mandate=mandate)
        key = "call_digest_match" if digest == record["digest"] else "call_digest_MISMATCH"
        tally[key] += 1
        if digest != record["digest"]:
            failures.append(f"{path.name} t{tick} {seat} attempt {record.get('attempt')}")
    result = next((r for r in records if r.get("kind") == "result"), None)
    if result is not None:
        logged = {k: v for k, v in result.items() if k not in ("kind", "utc")}
        replayed = json.loads(json.dumps(settle(fold_mod.fold(scenario, events)), default=str))
        same = replayed == json.loads(json.dumps(logged, default=str))
        tally["result_match" if same else "result_MISMATCH"] += 1
        if not same:
            failures.append(f"{path.name} result")
    wire = path.parent.parent / "wire_receipts" / path.name
    if wire.exists():
        rebuilt = wire_messages_by_seat(scenario, events, records, meta, five_model=five_model)
        receipts: dict[str, dict[int, str]] = defaultdict(dict)
        for row in read_jsonl(wire):
            receipts[row["seat"]][int(row["call_index"])] = row["prompt_sha256"]
        for seat, logged in receipts.items():
            for index, sha in sorted(logged.items()):
                ours = rebuilt[seat][index] if index < len(rebuilt[seat]) else None
                tally["wire_match" if ours == sha else "wire_MISMATCH"] += 1
                if ours != sha:
                    failures.append(f"{path.name} wire {seat} call {index}")


def iter_logs(paths: list[str]):
    for raw in paths:
        path = Path(raw)
        files = [path] if path.is_file() else sorted(path.rglob("*.jsonl"))
        for file in files:
            if file.parent.name == "wire_receipts" or file.name == "journal.jsonl":
                continue
            with file.open("r", encoding="utf-8") as handle:
                first = handle.readline()
            if '"kind": "meta"' in first:
                yield file


def check_v2_campaign(root: Path, salt: str, tally: Counter, failures: list) -> None:
    episodes = {row["episode_id"]: row for row in
                json.loads((root / "s0" / "episodes.json").read_text("utf-8"))["episodes"]}
    loaded: dict[str, tuple] = {}

    def episode(eid: str):
        if eid not in loaded:
            path = root / "s0" / "trajectories" / f"{eid}.jsonl"
            records = read_jsonl(path)
            meta = next(r for r in records if r.get("kind") == "meta")
            events = load_events(records)
            loaded[eid] = (scenario_for_log(meta, events), events, records)
        return loaded[eid]

    seen: set = set()
    for stage in ("s1", "s2"):
        for row in read_jsonl(root / stage / "journal.jsonl"):
            key = (stage, row["episode_id"], row["tick"], row.get("view"))
            if key in seen or "input_sha256" not in row:
                continue
            seen.add(key)
            scenario, events, records = episode(row["episode_id"])
            tick = int(row["tick"])
            priorities = episodes[row["episode_id"]]["priorities"]
            state = fold_mod.state_at(scenario, events, tick)
            if row.get("view") is None:
                _, _, digest = decision_prompt(
                    scenario, events, tick, mandate=f"priority:{priorities[state.mover]}")
            else:
                views = build_decision_views(
                    scenario, events, records, predicted_tick=tick,
                    shuffle_salt=salt, priorities=priorities)
                digest = prompt_digest(forecast_system_block(scenario),
                                       views.rendered[row["view"]])
            ok = digest == row["input_sha256"]
            tally[f"{stage}_input_match" if ok else f"{stage}_input_MISMATCH"] += 1
            if not ok:
                failures.append(f"{stage} {row['episode_id']} t{tick} {row.get('view')}")
            same_state = state_digest(state) == row["state_sha256"]
            tally[f"{stage}_state_match" if same_state else f"{stage}_state_MISMATCH"] += 1
    for path in sorted((root / "s4" / "cells").glob("*.json")):
        cell = json.loads(path.read_text("utf-8"))
        scenario, events, _records = episode(cell["episode_id"])
        brief = partner_brief_line(cell["partner_priorities"], cell["seat"])
        _, _, digest = decision_prompt(
            scenario, events, int(cell["tick"]),
            mandate=f"priority:{cell['priority_id']}", extra_user_line=brief or None)
        ok = digest == cell["input_sha256"]
        tally["s4_input_match" if ok else "s4_input_MISMATCH"] += 1
        if not ok:
            failures.append(f"s4 {cell['cell_id']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--logs", nargs="*", default=[],
                    help="episode log files or directories (searched recursively)")
    ap.add_argument("--five-model-corrective", action="store_true",
                    help="rebuild corrective re-prompts with the five-model study's repair text")
    ap.add_argument("--v2-campaign", default=None,
                    help="a forge_trio_v2_campaign_001 directory (s0, s1, s2, s4)")
    ap.add_argument("--shuffle-salt", default=None,
                    help="the campaign's view_schedule salt (keys B2_shuffled)")
    args = ap.parse_args()

    tally: Counter = Counter()
    failures: list[str] = []
    for path in iter_logs(args.logs):
        check_log(path, tally, failures, five_model=args.five_model_corrective)
    if args.v2_campaign:
        if not args.shuffle_salt:
            ap.error("--v2-campaign needs --shuffle-salt")
        check_v2_campaign(Path(args.v2_campaign), args.shuffle_salt, tally, failures)
    print(json.dumps({"tally": dict(sorted(tally.items())),
                      "failures": failures[:50],
                      "failure_count": len(failures)}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
