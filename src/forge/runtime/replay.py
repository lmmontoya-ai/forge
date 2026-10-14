"""Freeze a decision, re-sample the policy.  The world side replays from
the event log alone; the model side re-answers the byte-identical prompt N
times.  Single-provider validity rule enforced: a batch served by more than
one provider is invalid and must be re-collected.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

from ..core import actions as actions_mod
from ..core.events import Action, Event
from ..core import fold as fold_mod
from ..render.render import append_user_section, render_user, system_block
from ..variants.registry import mover_reminder
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


def decision_prompt(scenario, events, tick: int, *,
                    mandate: str = "principal",
                    extra_user_line: str | None = None) -> tuple[bytes, str, str]:
    """(system bytes, user text, digest) of the mover's prompt at `tick`.

    The prompt is the acting prompt: for a forge.variants mandate the
    variant reminder is appended to the user prompt exactly as `ModelAgent`
    appends it, and `extra_user_line` (if any) after it.  The digest covers
    every byte sent: sha256(system + newline + user).
    """
    st = fold_mod.state_at(scenario, events, tick)
    prefix = tuple(ev for ev in events if ev.tick < tick)
    system = system_block(scenario, mandate)
    user = render_user(st, prefix, st.mover)
    reminder = mover_reminder(mandate)
    if reminder:
        user = append_user_section(user, reminder)
    if extra_user_line is not None:
        user = append_user_section(user, extra_user_line)
    digest = hashlib.sha256(system + b"\n" + user.encode("utf-8")).hexdigest()
    return system, user, digest


def sample_policy(client, spec, scenario, events, tick: int, *,
                  n: int, meter=None, mandate: str = "principal",
                  parallel: int = 1,
                  extra_user_line: str | None = None,
                  on_draw: Callable[[int, Action | None, list, list], None] | None = None,
                  ) -> PolicyBatch:
    """N independent draws of the mover's policy at a frozen decision,
    each answering the `decision_prompt` bytes.  Draws share nothing but
    the meter, so `parallel` fans them out across threads (replay stages
    are embarrassingly parallel; the single-provider validity rule is
    checked over the merged batch as always).  Results merge in draw order
    regardless of completion order."""
    st = fold_mod.state_at(scenario, events, tick)
    seat = st.mover
    system, user, digest = decision_prompt(
        scenario, events, tick, mandate=mandate, extra_user_line=extra_user_line)
    base = [
        {"role": "system",
         "content": system.decode("utf-8")},
        {"role": "user", "content": user},
    ]
    tools = load_tools()

    def one_draw(draw_index: int):
        messages = list(base)
        action = None
        records, providers = [], []
        for _attempt in range(MAX_BAD_OUTPUTS):
            if meter is not None:
                meter.check()
            result = client.chat(spec, messages, tools)
            records.append(result)
            providers.append(result.provider)
            candidate, error, msg = parse_reply(result)
            if candidate is not None:
                reason = actions_mod.validate(st, seat, candidate)
                if reason is None:
                    action = candidate
                    if meter is not None:
                        try:
                            meter.add(result, spec)
                        except Exception:
                            if on_draw is not None:
                                on_draw(draw_index, action, records, providers)
                            raise
                    break
                error = f"illegal action: {reason}"
            if meter is not None:
                try:
                    meter.add(result, spec)
                except Exception:
                    if on_draw is not None:
                        on_draw(draw_index, action, records, providers)
                    raise
            messages = messages + corrective(msg, error)
        if on_draw is not None:
            on_draw(draw_index, action, records, providers)
        return action, records, providers

    batch = PolicyBatch(tick=tick, seat=seat, digest=digest)
    if parallel > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            results = list(pool.map(one_draw, range(n)))
    else:
        results = [one_draw(i) for i in range(n)]
    for action, records, providers in results:
        batch.records.extend(records)
        batch.providers.extend(providers)
        if action is None:
            action = Action("WAIT", {})
            batch.invalid_draws += 1
        batch.actions.append(action)
    served = {p for p in batch.providers if p is not None}
    batch.valid = len(served) <= 1
    return batch
