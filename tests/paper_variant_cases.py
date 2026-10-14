"""Synthetic cases that pin the paper variants' prompts, episodes and views.

Shared by `tests/test_variants.py` (which compares this checkout with
`tests/golden/paper_variants.json`) and `scripts/verify_variant_equivalence.py`
(which runs the same cases through the study repository's original
implementation and writes that golden file).  Everything here must also
run against the original FORGE commit, so it imports only APIs that exist
there, and only inside functions.

`ScriptedModelClient` stands in for a provider: it answers each chat call
with a tool call chosen from the scenario's cooperative plan, keyed on a
hash of the exact messages, so two implementations that send identical
prompts play identical episodes.  Its "reasoning" echoes the end of the
user prompt (where a variant's private reminder sits) so the reader trace
rungs and their redaction are exercised.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path

SHUFFLE_SALT = "forge-variant-equivalence"
ASSIGN_SALT = "forge-variant-assignment"
VIEW_TICKS = (4, 10, 16, 22, 23, 29, 36)
REPLAY_TICKS = (5, 13, 22, 31)
#: The views a reader was ever served in the hidden-priority campaign or
#: that are meant to be free of priority wording (all but C_goal, L4, L4_full).
AUDITED_VIEWS = ("B0", "B1_count", "B2_ordered", "B2_shuffled", "L0", "L1",
                 "L2", "L3", "L4_redacted", "C_args")

FAMILIES = ("v1", "v2", "v3", "clear")

#: Mandates whose system blocks are pinned over every bank scenario.
SYSTEM_MANDATES = {
    "v1": ("principal", "own", "joint"),
    "v2": ("principal", "priority:P_SHIP", "priority:P_GUARD", "priority:P_ALIGN"),
    "v3": ("priority:P_SHIP", "priority:P_GUARD", "priority:P_ALIGN",
           "sham:COBALT", "sham:MAROON", "sham:BRONZE"),
    "clear": ("clear-goal:P_SHIP", "clear-goal:P_GUARD", "clear-goal:P_ALIGN",
              "clear-sham:COBALT", "clear-sham:MAROON", "clear-sham:BRONZE"),
}

#: (episode id, bank index, extended, seat -> mandate)
EPISODES = {
    "v1": (("forge-v1-verify-00", 5, False,
            {"API": "principal", "DATA": "principal", "QA": "principal"}),),
    "v2": (("forge-v2-verify-00", 0, True,
            {"API": "priority:P_SHIP", "DATA": "priority:P_GUARD", "QA": "priority:P_ALIGN"}),
           ("forge-v2-verify-01", 11, True,
            {"API": "priority:P_ALIGN", "DATA": "priority:P_SHIP", "QA": "priority:P_GUARD"})),
    "v3": (("p3fg-verify-00", 3, True,
            {"API": "priority:P_GUARD", "DATA": "priority:P_ALIGN", "QA": "priority:P_SHIP"}),
           ("p3fg-verify-01", 17, True,
            {"API": "sham:BRONZE", "DATA": "sham:COBALT", "QA": "sham:MAROON"})),
    "clear": (("p3fgc-verify-00", 8, True,
               {"API": "clear-goal:P_ALIGN", "DATA": "clear-goal:P_SHIP",
                "QA": "clear-goal:P_GUARD"}),
              ("p3fgc-verify-01", 20, True,
               {"API": "clear-sham:MAROON", "DATA": "clear-sham:BRONZE",
                "QA": "clear-sham:COBALT"})),
}

_TURN = re.compile(r"turn (\d+)/(\d+) · your move · you are (\w+)")


def sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


class ScriptedModelClient:
    """A zero-cost provider stand-in with the OpenRouterClient.chat signature."""

    def __init__(self, scenario):
        from forge.policies.scripted import PLANS
        self.plan = PLANS["cooperative"](scenario)
        self.calls: list[str] = []

    def chat(self, spec, messages, tools=None):
        from forge.core.events import SEATS
        from forge.runtime.openrouter import CallResult

        blob = canonical(messages)
        self.calls.append(sha(blob))
        user = messages[1]["content"]
        match = _TURN.search(user)
        tick, seat = int(match.group(1)), match.group(3)
        key = hashlib.sha256(blob.encode("utf-8")).digest()
        if len(messages) > 2:
            name, args = "wait", {}           # after a rejection, recover
        else:
            planned = self.plan.get(seat, {}).get(tick)
            choice = key[0] % 8
            if planned is not None and choice < 5:
                name, args = planned.name.lower(), planned.args
            elif choice == 5:
                name, args = "read", {"path": "common.py"}
            elif choice == 6:
                name, args = "run", {}
            else:
                other = SEATS[(SEATS.index(seat) + 1) % 3]
                name, args = "query", {"to": other,
                                       "text": "Which ERR_KEY value are you using?"}
        reasoning = f"{user[-400:].strip()} So I will {name} now."
        raw = {
            "id": f"scripted-{len(self.calls)}",
            "model": spec.slug,
            "provider": "scripted",
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_details": [{"type": "reasoning.text", "text": reasoning}],
                    "tool_calls": [{
                        "id": f"call_{len(self.calls)}",
                        "type": "function",
                        "function": {"name": name,
                                     "arguments": json.dumps(args, sort_keys=True)},
                    }],
                },
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
        return CallResult(raw=raw, provider="scripted", model=spec.slug,
                          usage=raw["usage"], cost_usd=0.0, latency_s=0.0,
                          attempts=1)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def compute_family(backend, family: str, workdir: Path) -> dict:
    """Run one family's cases through `backend` and return comparable output."""
    from forge.runtime.replay import load_events
    from forge.scenarios.bank import load_bank

    bank = load_bank("v1")
    out: dict = {"system_blocks": {}, "episodes": {}, "views": {}, "replay": {},
                 "extension_params": dataclasses.asdict(backend.extend(bank[0]).params)}
    for mandate in SYSTEM_MANDATES[family]:
        out["system_blocks"][mandate] = [
            sha(backend.system_block(backend.extend(sc) if family != "v1" else sc, mandate))
            for sc in bank
        ]
    for eid, index, extended, mandates in EPISODES[family]:
        scenario = backend.extend(bank[index]) if extended else bank[index]
        client = ScriptedModelClient(scenario)
        log_dir = workdir / family
        backend.run_episode(scenario, mandates, eid, log_dir, client)
        records = read_jsonl(log_dir / f"{eid}.jsonl")
        events = load_events(records)
        calls = [r for r in records if r.get("kind") == "call"]
        result = next(r for r in records if r.get("kind") == "result")
        out["episodes"][eid] = {
            "messages": client.calls,
            "digests": [r.get("digest") for r in calls],
            "events": sha(canonical([[e.tick, e.seat, e.action.name, e.action.args,
                                      e.invalid, e.truncated] for e in events])),
            "result": {k: v for k, v in result.items() if k not in ("kind", "utc")},
        }
        priorities = {seat: m.split(":", 1)[1] for seat, m in mandates.items()
                      if m.startswith("priority:")}
        if family in ("v1", "v2"):
            for tick in VIEW_TICKS:
                out["views"][f"{eid}@{tick}"] = backend.decision_views(
                    scenario, events, records, tick, priorities or None)
        if family == "v2":
            for tick in REPLAY_TICKS:
                out["replay"][f"{eid}@{tick}"] = backend.replay_prompts(
                    scenario, events, tick, priorities)
    if family == "v2":
        out["assignments"] = {
            f"{mode}:{eid}": backend.assign(eid, mode)
            for mode in ("permutation", "iid")
            for eid in ("e0", "e1", "e2", "forge-v2-00")
        }
    return out


def compact(output: dict) -> dict:
    """Fold long digest lists into one digest each, for the golden file."""
    out = json.loads(canonical(output))
    for episode in out["episodes"].values():
        for key in ("messages", "digests"):
            episode[key] = {"count": len(episode[key]), "sha256": sha(canonical(episode[key]))}
    for mandate, values in out["system_blocks"].items():
        out["system_blocks"][mandate] = sha(canonical(values))
    return out


class PortedBackend:
    """This checkout's implementation of the paper variants."""

    def extend(self, scenario):
        from forge.variants import extend_scenario
        return extend_scenario(scenario)

    def system_block(self, scenario, mandate: str) -> bytes:
        from forge.render.render import system_block
        return system_block(scenario, mandate)

    def run_episode(self, scenario, mandates, episode_id, log_dir, client) -> None:
        from forge.runtime.agents import ModelAgent
        from forge.runtime.config import ModelSpec
        from forge.runtime.episode import run_episode
        spec = ModelSpec(slug="scripted/model")
        agents = {seat: ModelAgent(spec, client, mandate=mandate)
                  for seat, mandate in mandates.items()}
        run_episode(scenario, agents, log_dir, bank="v1", episode_id=episode_id)

    def decision_views(self, scenario, events, records, tick, priorities) -> dict:
        from forge.core import fold as fold_mod
        from forge.reader.decision import build_decision_views, forecast_system_block
        from forge.reader.evidence import prompt_digest
        from forge.variants.hidden_priority import audit_public_views, public_corpus
        views = build_decision_views(scenario, events, records, predicted_tick=tick,
                                     shuffle_salt=SHUFFLE_SALT, priorities=priorities)
        system = forecast_system_block(scenario)
        state = fold_mod.state_at(scenario, events, tick)
        served = {name: text for name, text in views.rendered.items() if name in AUDITED_VIEWS}
        return {
            "forecast_system": sha(system),
            "views": {name: sha(text) for name, text in views.rendered.items()},
            "inputs": {name: prompt_digest(system, text) for name, text in views.rendered.items()},
            "state": views.state_sha256_before,
            "mover": state.mover,
            "trace_kinds": list(views.blocks.trace_kinds),
            "audit": audit_public_views(served, corpus=public_corpus(scenario), exempt=()),
        }

    def replay_prompts(self, scenario, events, tick, priorities) -> dict:
        from forge.core import fold as fold_mod
        from forge.runtime.replay import decision_prompt
        from forge.variants.hidden_priority import PRIORITY_IDS, partner_brief_line
        seat = fold_mod.state_at(scenario, events, tick).mover
        mandate = f"priority:{priorities[seat]}"
        wrong = {s: PRIORITY_IDS[(PRIORITY_IDS.index(p) + 1) % 3]
                 for s, p in priorities.items() if s != seat}
        true = {s: p for s, p in priorities.items() if s != seat}
        out = {"plain": decision_prompt(scenario, events, tick, mandate=mandate)[2]}
        for arm, partners in (("partner_true", true), ("partner_wrong", wrong)):
            out[arm] = decision_prompt(
                scenario, events, tick, mandate=mandate,
                extra_user_line=partner_brief_line(partners, seat))[2]
        return out

    def assign(self, episode_id: str, mode: str) -> dict:
        from forge.variants.hidden_priority import assign_priorities
        return assign_priorities(episode_id, salt=ASSIGN_SALT, mode=mode)
