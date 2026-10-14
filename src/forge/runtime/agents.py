"""Agents: a model behind OpenRouter, or a scripted policy, behind one
interface: act(game, seat, logger, meter) -> Action.  §8.3-equivalent
handling: no tool call, unknown tool, bad arguments, and legal-shape-
illegal-move each earn a re-prompt with the specific reason; after three
failures the tick records WAIT with invalid=true.  Provider failure never
reaches this table.
"""
from __future__ import annotations

from ..core import actions as actions_mod
from ..core.events import Action
from ..render.render import append_user_section, render_user, system_block
from ..variants.registry import mover_reminder
from .openrouter import CallResult
from .tools import action_from_tool_call, load_tools

MAX_BAD_OUTPUTS = 3


def parse_reply(result: CallResult):
    msg = result.message()
    calls = msg.get("tool_calls") or []
    if not calls:
        return None, "no tool call in reply", msg
    if len(calls) != 1:
        return None, f"reply contained {len(calls)} tool calls; exactly one is required", msg
    fn = calls[0].get("function") or {}
    try:
        return action_from_tool_call(fn.get("name", ""),
                                     fn.get("arguments", "{}")), None, msg
    except ValueError as e:
        return None, str(e), msg


def corrective(assistant_msg: dict, error: str) -> list:
    note = (f"That was rejected: {error}. "
            "Reply with exactly one legal action as a tool call.")
    calls = assistant_msg.get("tool_calls") or []
    if calls:
        assistant = {"role": "assistant",
                     "content": assistant_msg.get("content"),
                     "tool_calls": calls}
        rejections = [{"role": "tool", "tool_call_id": c.get("id", f"call_{i}"),
                       "content": note} for i, c in enumerate(calls)]
        return [assistant] + rejections
    return [{"role": "assistant", "content": assistant_msg.get("content") or ""},
            {"role": "user", "content": note}]


class ScriptedAgent:
    def __init__(self, name: str, policy):
        self.name = name
        self.policy = policy

    def describe(self) -> dict:
        return {"kind": "scripted", "name": self.name}

    def act(self, game, seat: str, logger=None, meter=None) -> Action:
        try:
            a = self.policy(game, seat)
        except Exception:
            a = Action("WAIT", {})
        if actions_mod.validate(game.state, seat, a) is not None:
            a = Action("WAIT", {})
        return a


class ModelAgent:
    def __init__(self, spec, client, *, mandate: str = "principal",
                 inject_fn=None):
        """`mandate`: a registered mandates.json variant, or a prefixed
        forge.variants mandate (`priority:P_SHIP`, ...).  A variant mandate
        replaces the system block's Mandate paragraph and appends its
        private reminder to the end of this seat's user prompt.

        `inject_fn(game, seat) -> str | None`: an extra section appended
        to the user prompt for this seat's calls (the F5/F9 forecast or
        filler line).  The injected text is logged with the call; the
        prompt digest recorded is of the UNINJECTED render (system block
        plus `render_user`, without the variant reminder or the
        injection), with the injection stored beside it.  The reminder is a
        pure function of the mandate recorded in the episode meta, so
        replay reconstructs all three."""
        self.spec = spec
        self.client = client
        self.mandate = mandate
        self.inject_fn = inject_fn

    def describe(self) -> dict:
        return {"kind": "model", "mandate": self.mandate,
                **self.spec.describe()}

    def act(self, game, seat: str, logger=None, meter=None) -> Action:
        state, events = game.state, tuple(game.events)
        from ..render.render import render_prompt
        _, digest = render_prompt(state, events, seat, mandate=self.mandate)
        user = render_user(state, events, seat)
        reminder = mover_reminder(self.mandate)
        if reminder:
            user = append_user_section(user, reminder)
        injected = self.inject_fn(game, seat) if self.inject_fn else None
        if injected:
            user = f"{user}\n## Forecast\n{injected}\n"
            if logger:
                logger.write({"kind": "injection", "tick": state.tick + 1,
                              "seat": seat, "text": injected})
        messages = [
            {"role": "system",
             "content": system_block(game.scenario,
                                     self.mandate).decode("utf-8")},
            {"role": "user", "content": user},
        ]
        tools = load_tools()
        last_error = "no attempt"
        for attempt in range(1, MAX_BAD_OUTPUTS + 1):
            if meter is not None:
                meter.check()
            result = self.client.chat(self.spec, messages, tools)
            action, error, msg = parse_reply(result)
            if action is not None:
                reason = actions_mod.validate(state, seat, action)
                if reason is None:
                    if logger:
                        logger.call(tick=state.tick + 1, seat=seat,
                                    digest=digest, model=self.describe(),
                                    attempt=attempt, purpose="act",
                                    result=result)
                    if meter is not None:
                        meter.add(result, self.spec)
                    return action
                error = f"illegal action: {reason}"
            last_error = error
            if logger:
                logger.call(tick=state.tick + 1, seat=seat, digest=digest,
                            model=self.describe(), attempt=attempt,
                            purpose="act", result=result, error=error)
            if meter is not None:
                meter.add(result, self.spec)
            messages = messages + corrective(msg, error)
        if logger:
            logger.call(tick=state.tick + 1, seat=seat, digest=digest,
                        model=self.describe(), attempt=MAX_BAD_OUTPUTS,
                        purpose="act", error=last_error, invalid_wait=True)
        return Action("WAIT", {"__invalid__": True})
