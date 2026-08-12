"""Freeze a decision, re-sample the policy.  The world side replays from
the event log alone; the model side re-answers the byte-identical prompt N
times.  Single-provider validity rule enforced: a batch served by more than
one provider is invalid and must be re-collected.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core import actions as actions_mod
from ..core.events import Action, Event
from ..core import fold as fold_mod
from ..render.render import render_prompt, render_user, system_block
from .agents import MAX_BAD_OUTPUTS, corrective, parse_reply
from .tools import load_tools


def load_events(records: list) -> list:
    return [Event(r["tick"], r["seat"],
                  Action(r["action"]["name"], r["action"]["args"]),
                  invalid=r.get("invalid", False),
                  truncated=r.get("truncated", False))
            for r in records if r.get("kind") == "event"]


@dataclass
class PolicyBatch:
    tick: int
    seat: str
    digest: str
    actions: list = field(default_factory=list)
    invalid_draws: int = 0
    providers: list = field(default_factory=list)
    valid: bool = True
    records: list = field(default_factory=list)


def sample_policy(client, spec, scenario, events, tick: int, *,
                  n: int, meter=None,
                  mandate: str = "principal") -> PolicyBatch:
    st = fold_mod.state_at(scenario, events, tick)
    seat = st.mover
    prefix = tuple(ev for ev in events if ev.tick < tick)
    _, digest = render_prompt(st, prefix, seat, mandate=mandate)
    base = [
        {"role": "system",
         "content": system_block(scenario, mandate).decode("utf-8")},
        {"role": "user", "content": render_user(st, prefix, seat)},
    ]
    tools = load_tools()
    batch = PolicyBatch(tick=tick, seat=seat, digest=digest)
    for _ in range(n):
        messages = list(base)
        action = None
        for _attempt in range(MAX_BAD_OUTPUTS):
            result = client.chat(spec, messages, tools)
            if meter is not None:
                meter.add(result, spec)
            batch.records.append(result)
            batch.providers.append(result.provider)
            candidate, error, msg = parse_reply(result)
            if candidate is not None:
                reason = actions_mod.validate(st, seat, candidate)
                if reason is None:
                    action = candidate
                    break
                error = f"illegal action: {reason}"
            messages = messages + corrective(msg, error)
        if action is None:
            action = Action("WAIT", {})
            batch.invalid_draws += 1
        batch.actions.append(action)
    served = {p for p in batch.providers if p is not None}
    batch.valid = len(served) <= 1
    return batch
