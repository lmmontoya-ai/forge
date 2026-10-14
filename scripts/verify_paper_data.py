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
                 replay), S2 (reader view), S3 (objective inference) and
                 S4 (partner-brief replay) cell, and of any further reader
                 journal on the same positions (--reader-journal).  S3 is
                 also checked against tests/golden/v2_objective_inference.json
                 and, with --menu-salt, its letter orders are recomputed.
  ordinary panel the nine-forecaster panel's situation (B0) and full-record
                 (L3) reader prompts at the 64 decisions of the v1 trio
                 campaign, against tests/golden/ordinary_panel_forge.json
                 and, if given, the study's panel manifest.
  five-model     every game of the five-model clear-goal study replayed
                 through ModelAgent with the COMMIT form each seat used
                 (forge.runtime.commit_forms), answering each call with the
                 recorded response: the rebuilt log, every outbound message
                 list (wire receipts) and the tool schema each seat was sent.

Usage:
  python scripts/verify_paper_data.py --logs DIR [DIR ...]
  python scripts/verify_paper_data.py --v2-campaign DIR --shuffle-salt HEX [--menu-salt HEX]
  python scripts/verify_paper_data.py --ordinary-panel AMEND5_DIR [--panel-manifest JSON]
  python scripts/verify_paper_data.py --five-model-replay S0_DIR

The data directories belong to the study repository and are not shipped
with FORGE.  The script exits non-zero if any comparison fails.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.core import fold as fold_mod                             # noqa: E402
from forge.grading.scoring import settle                            # noqa: E402
from forge.reader.decision import (                                 # noqa: E402
    build_decision_views, forecast_system_block, state_digest)
from forge.reader.evidence import prompt_digest                     # noqa: E402
from forge.reader.objective import (                                # noqa: E402
    objective_menu, objective_system_block, render_objective_view)
from forge.render.render import (                                   # noqa: E402
    append_user_section, render_prompt, render_user, system_block)
from forge.runtime.agents import ModelAgent, corrective             # noqa: E402
from forge.runtime.commit_forms import (                            # noqa: E402
    EMPTY_COMMIT_ERROR, commit_tools, repair_corrective)
from forge.runtime.config import ModelSpec                          # noqa: E402
from forge.runtime.episode import run_episode                       # noqa: E402
from forge.runtime.openrouter import CallResult                     # noqa: E402
from forge.runtime.replay import decision_prompt, load_events       # noqa: E402
from forge.runtime.tools import load_tools                          # noqa: E402
from forge.scenarios.bank import load_bank                          # noqa: E402
from forge.variants import extend_scenario, mover_reminder          # noqa: E402
from forge.variants.hidden_priority import partner_brief_line       # noqa: E402

GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "golden"
PANEL_GOLDEN = GOLDEN / "ordinary_panel_forge.json"
OBJECTIVE_GOLDEN = GOLDEN / "v2_objective_inference.json"

# The nine-forecaster panel served B0 as its situation view and L3 as its
# full-record view, with this shuffle salt (no shuffled view was served).
PANEL_SALT = "ordinary-prediction-panel:v1"
PANEL_VIEWS = {"situation": "B0", "full_record": "L3"}

# The five-model clear-goal study sent these seats the `entries` COMMIT
# form and every other seat `nonempty-map`.
FIVE_MODEL_ENTRY_SLUGS = frozenset({"google/gemini-3.7-flash", "x-ai/grok-4.5"})

_BANKS: dict[str, dict] = {}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def canonical_sha256(value) -> str:
    """SHA-256 of canonical JSON: the digest of a message list in the
    clear-goal wire receipts and the panel manifest."""
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        out[seat].append(canonical_sha256(messages))
        error = record.get("error")
        if error:
            msg = (record["raw"].get("choices") or [{}])[0].get("message") or {}
            extra = corrective(msg, error)
            if five_model:
                extra = repair_corrective(extra, error)
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


def check_v2_campaign(root: Path, salt: str, tally: Counter, failures: list,
                      reader_journals: tuple = (), menu_salt: str | None = None) -> None:
    episodes = {row["episode_id"]: row for row in
                json.loads((root / "s0" / "episodes.json").read_text("utf-8"))["episodes"]}
    loaded: dict[str, tuple] = {}
    view_cache: dict[tuple, object] = {}

    def episode(eid: str):
        if eid not in loaded:
            path = root / "s0" / "trajectories" / f"{eid}.jsonl"
            records = read_jsonl(path)
            meta = next(r for r in records if r.get("kind") == "meta")
            events = load_events(records)
            loaded[eid] = (scenario_for_log(meta, events), events, records)
        return loaded[eid]

    def views_at(eid: str, tick: int):
        if (eid, tick) not in view_cache:
            scenario, events, records = episode(eid)
            view_cache[eid, tick] = build_decision_views(
                scenario, events, records, predicted_tick=tick,
                shuffle_salt=salt, priorities=episodes[eid]["priorities"])
        return view_cache[eid, tick]

    seen: set = set()
    journals = [(stage, root / stage / "journal.jsonl") for stage in ("s1", "s2")]
    journals += [(f"reader:{Path(j).parent.name}", Path(j)) for j in reader_journals]
    for stage, journal in journals:
        for row in read_jsonl(journal):
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
                views = views_at(row["episode_id"], tick)
                digest = prompt_digest(forecast_system_block(scenario),
                                       views.rendered[row["view"]])
            ok = digest == row["input_sha256"]
            tally[f"{stage}_input_match" if ok else f"{stage}_input_MISMATCH"] += 1
            if not ok:
                failures.append(f"{stage} {row['episode_id']} t{tick} {row.get('view')}")
            same_state = state_digest(state) == row["state_sha256"]
            tally[f"{stage}_state_match" if same_state else f"{stage}_state_MISMATCH"] += 1
    check_objective_inference(root, episode, views_at, tally, failures, menu_salt)
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


def _count(tally: Counter, failures: list, name: str, ok: bool, what: str) -> None:
    tally[f"{name}_match" if ok else f"{name}_MISMATCH"] += 1
    if not ok:
        failures.append(what)


def check_objective_inference(root: Path, episode, views_at, tally: Counter,
                              failures: list, menu_salt: str | None) -> None:
    """S3: every cell's objective-inference prompt, from forge.reader.objective."""
    journal = root / "s3" / "journal.jsonl"
    if not journal.exists():
        return
    pinned_file = json.loads(OBJECTIVE_GOLDEN.read_text("utf-8"))
    golden = {row["cell_id"]: row for row in pinned_file["cells"]}
    for eid, sha in sorted(pinned_file["trajectory_sha256"].items()):
        path = root / "s0" / "trajectories" / f"{eid}.jsonl"
        _count(tally, failures, "s3_trajectory_sha256", file_sha256(path) == sha,
               f"s3 trajectory {eid}")
    cells: dict[str, dict] = {}
    for row in read_jsonl(journal):
        first = cells.setdefault(row["cell_id"], row)
        _count(tally, failures, "s3_draw_consistent",
               (row["input_sha256"], row["menu"]) == (first["input_sha256"], first["menu"]),
               f"s3 draws differ {row['cell_id']}")
    _count(tally, failures, "s3_cell_set_vs_golden", set(cells) == set(golden),
           "s3 cell set differs from the golden file")
    for cell_id, row in sorted(cells.items()):
        scenario, events, _records = episode(row["episode_id"])
        tick = int(row["tick"])
        menu = [tuple(item) for item in row["menu"]]
        user = render_objective_view(views_at(row["episode_id"], tick).blocks,
                                     row["view"], menu)
        digest = prompt_digest(objective_system_block(scenario), user)
        _count(tally, failures, "s3_input", digest == row["input_sha256"],
               f"s3 {cell_id} input")
        state = fold_mod.state_at(scenario, events, tick)
        _count(tally, failures, "s3_state", state_digest(state) == row["state_sha256"],
               f"s3 {cell_id} state")
        pinned = golden.get(cell_id, {})
        _count(tally, failures, "s3_golden",
               (pinned.get("input_sha256"), pinned.get("state_sha256"), pinned.get("menu"))
               == (digest, row["state_sha256"], row["menu"]), f"s3 {cell_id} golden")
        if menu_salt:
            _count(tally, failures, "s3_menu",
                   objective_menu(menu_salt, cell_id.removeprefix("s3:")) == menu,
                   f"s3 {cell_id} menu")
    for path in sorted((root / "s3" / "cells").glob("*.json")):
        cell = json.loads(path.read_text("utf-8"))
        recorded = cells.get(cell["cell_id"], {}).get("input_sha256")
        _count(tally, failures, "s3_cell_file", cell["input_sha256"] == recorded,
               f"s3 cell file {path.name}")


def panel_messages(scenario, events, records, tick: int) -> dict[str, list]:
    """The panel's two reader prompts at one frozen decision."""
    views = build_decision_views(scenario, events, records, predicted_tick=tick,
                                 shuffle_salt=PANEL_SALT)
    system = forecast_system_block(scenario).decode("utf-8")
    return {name: [{"role": "system", "content": system},
                   {"role": "user", "content": views.rendered[view]}]
            for name, view in PANEL_VIEWS.items()}


def manifest_digests(manifest: dict) -> dict[tuple[str, str], set]:
    out: dict[tuple[str, str], set] = defaultdict(set)
    for cell in manifest["cells"]:
        out[cell["position_id"], cell["view"]].add(cell["prompt_sha256"])
    return out


def check_ordinary_panel(source: Path, tally: Counter, failures: list,
                         manifest: dict | None = None, golden: dict | None = None) -> None:
    """Rebuild the nine-forecaster panel's Engineering prompts.

    `source` is the v1 trio campaign directory (`selection.json` and
    `trajectories/`).  The recomputed digests must equal the golden file and,
    if given, every cell of the study's panel manifest.
    """
    golden = golden or json.loads(PANEL_GOLDEN.read_text("utf-8"))
    pinned = {row["position_id"]: row for row in golden["positions"]}
    if manifest is not None:
        recorded = manifest_digests(manifest)
        _count(tally, failures, "panel_manifest_positions",
               {pid for pid, _view in recorded} == set(pinned),
               "panel manifest positions differ from the golden file")
        for pid, row in sorted(pinned.items()):
            for name in PANEL_VIEWS:
                _count(tally, failures, "panel_golden_vs_manifest",
                       recorded.get((pid, name)) == {row[name]},
                       f"panel golden {pid} {name} vs manifest")
    selection = json.loads((source / "selection.json").read_text("utf-8"))
    rows = selection["natural"]
    _count(tally, failures, "panel_selection_positions",
           {f"{r['episode_id']}:t{int(r['tick'])}" for r in rows} == set(pinned),
           "panel selection positions differ from the golden file")
    logs: dict[Path, tuple] = {}
    for row in rows:
        pid = f"{row['episode_id']}:t{int(row['tick'])}"
        pin = pinned.get(pid, {})
        path = source / "trajectories" / re.split(r"[\\/]", row["log"])[-1]
        if path not in logs:
            records = read_jsonl(path)
            meta = next(r for r in records if r.get("kind") == "meta")
            events = load_events(records)
            logs[path] = (file_sha256(path), scenario_for_log(meta, events), events, records)
        sha, scenario, events, records = logs[path]
        _count(tally, failures, "panel_trajectory_sha256",
               sha == row["log_sha256"] == pin.get("trajectory_sha256"),
               f"panel {pid} trajectory")
        system_sha = hashlib.sha256(forecast_system_block(scenario)).hexdigest()
        _count(tally, failures, "panel_system", system_sha == pin.get("system_sha256"),
               f"panel {pid} system block")
        for name, messages in panel_messages(scenario, events, records,
                                             int(row["tick"])).items():
            _count(tally, failures, f"panel_{name}",
                   canonical_sha256(messages) == pin.get(name), f"panel {pid} {name}")


class ReplayClient:
    """Answers each chat call with this seat's next recorded response, and
    records the digests of the messages and tools it was sent."""

    def __init__(self, records: list[dict]):
        self.queue = [r for r in records if "raw" in r]
        self.messages: list[str] = []
        self.tools: list[str] = []

    def chat(self, spec, messages, tools=None):
        self.messages.append(canonical_sha256(messages))
        self.tools.append(canonical_sha256(tools))
        record = self.queue.pop(0)
        return CallResult(raw=copy.deepcopy(record["raw"]), provider=record.get("provider"),
                          model=record.get("served_model"), usage=record.get("usage"),
                          cost_usd=None, latency_s=record.get("latency_s"),
                          attempts=record.get("transport_attempts"))


def _comparable(records: list[dict]) -> list[dict]:
    """Log records without wall-clock time, code version, the recorded COMMIT
    form or the cost meter's spend record (the replay runs without a meter)."""
    out = []
    for record in records:
        if record.get("kind") == "spend":
            continue
        record = {k: v for k, v in record.items() if k not in ("utc", "code_version")}
        if record.get("kind") == "meta":
            record["seats"] = {seat: {k: v for k, v in desc.items() if k != "commit_form"}
                               for seat, desc in record["seats"].items()}
        if isinstance(record.get("model"), dict):
            record["model"] = {k: v for k, v in record["model"].items() if k != "commit_form"}
        out.append(record)
    return out


def five_model_form(slug: str) -> str:
    return "entries" if slug in FIVE_MODEL_ENTRY_SLUGS else "nonempty-map"


def check_five_model_replay(root: Path, tally: Counter, failures: list) -> None:
    """Replay each game through ModelAgent with the seat's COMMIT form."""
    for path in sorted((root / "trajectories").glob("*.jsonl")):
        records = read_jsonl(path)
        meta = next(r for r in records if r.get("kind") == "meta")
        events = load_events(records)
        scenario = scenario_for_log(meta, events)
        if scenario is None or not any(r.get("kind") == "result" for r in records):
            tally["five_model_logs_skipped"] += 1
            continue
        tally["five_model_logs"] += 1
        clients, agents, forms = {}, {}, {}
        for seat, desc in meta["seats"].items():
            spec = ModelSpec(slug=desc["slug"], label=desc["label"],
                             provider_order=tuple(desc["provider_order"]),
                             temperature=desc["temperature"], max_tokens=desc["max_tokens"],
                             reasoning=desc["reasoning"], tool_choice=desc["tool_choice"])
            forms[seat] = five_model_form(desc["slug"])
            tally[f"five_model_seats_{forms[seat]}"] += 1
            clients[seat] = ReplayClient([r for r in records if r.get("kind") == "call"
                                          and r.get("seat") == seat])
            agents[seat] = ModelAgent(spec, clients[seat], mandate=desc["mandate"],
                                      commit_form=forms[seat])
        tally["five_model_empty_commit_errors"] += sum(
            EMPTY_COMMIT_ERROR in (r.get("error") or "")
            for r in records if r.get("kind") == "call")
        with tempfile.TemporaryDirectory(prefix="forge-five-model-") as tmp:
            run_episode(scenario, agents, tmp, bank=meta["bank"],
                        episode_id=meta["episode_id"])
            rebuilt = read_jsonl(Path(tmp) / f"{meta['episode_id']}.jsonl")
        _count(tally, failures, "five_model_log", _comparable(rebuilt) == _comparable(records),
               f"five-model {path.name} log")
        receipts: dict[str, dict[int, str]] = defaultdict(dict)
        for row in read_jsonl(root / "wire_receipts" / path.name):
            receipts[row["seat"]][int(row["call_index"])] = row["prompt_sha256"]
        for seat, client in clients.items():
            logged = receipts.get(seat, {})
            _count(tally, failures, "five_model_wire_count", len(client.messages) == len(logged),
                   f"five-model {path.name} {seat} call count")
            for index, sha in sorted(logged.items()):
                ours = client.messages[index] if index < len(client.messages) else None
                _count(tally, failures, "five_model_wire", ours == sha,
                       f"five-model {path.name} wire {seat} call {index}")
            expected = canonical_sha256(commit_tools(load_tools(), forms[seat]))
            for digest in client.tools:
                _count(tally, failures, f"five_model_tools_{forms[seat]}", digest == expected,
                       f"five-model {path.name} {seat} tools")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--logs", nargs="*", default=[],
                    help="episode log files or directories (searched recursively)")
    ap.add_argument("--five-model-corrective", action="store_true",
                    help="rebuild corrective re-prompts with the repair sentence of the "
                         "non-default COMMIT forms (the five-model study)")
    ap.add_argument("--v2-campaign", default=None,
                    help="a forge_trio_v2_campaign_001 directory (s0 to s4)")
    ap.add_argument("--shuffle-salt", default=None,
                    help="the campaign's view_schedule salt (keys B2_shuffled)")
    ap.add_argument("--menu-salt", default=None,
                    help="the campaign's objective_menu_order salt (S3 letter orders)")
    ap.add_argument("--reader-journal", nargs="*", default=[],
                    help="further journals of cells on the v2 positions (e.g. the "
                         "evidence-compression reader collection)")
    ap.add_argument("--ordinary-panel", default=None,
                    help="the v1 trio campaign directory (forge_trio_fresh_001/amend5)")
    ap.add_argument("--panel-manifest", default=None,
                    help="the study's Engineering panel manifest (forge.json)")
    ap.add_argument("--five-model-replay", default=None,
                    help="the five-model clear-goal s0 directory (trajectories, wire_receipts)")
    args = ap.parse_args()

    tally: Counter = Counter()
    failures: list[str] = []
    for path in iter_logs(args.logs):
        check_log(path, tally, failures, five_model=args.five_model_corrective)
    if args.v2_campaign:
        if not args.shuffle_salt:
            ap.error("--v2-campaign needs --shuffle-salt")
        check_v2_campaign(Path(args.v2_campaign), args.shuffle_salt, tally, failures,
                          tuple(args.reader_journal), args.menu_salt)
    if args.ordinary_panel:
        manifest = (json.loads(Path(args.panel_manifest).read_text("utf-8"))
                    if args.panel_manifest else None)
        check_ordinary_panel(Path(args.ordinary_panel), tally, failures, manifest)
    if args.five_model_replay:
        check_five_model_replay(Path(args.five_model_replay), tally, failures)
    print(json.dumps({"tally": dict(sorted(tally.items())),
                      "failures": failures[:50],
                      "failure_count": len(failures)}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
