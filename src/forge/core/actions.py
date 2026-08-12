"""validate + apply, driven by spec/actions.v1.json (design §4, §3.5).

`validate(state, seat, action)` returns None when legal, else the specific
reason (which the runtime feeds back on re-prompt).  Effects live in
fold.apply; this module is the law.
"""
from __future__ import annotations

import re

from .events import SEATS
from .fold import State
from .scenario import ENGINE_ARTIFACTS

_PATH_RE = re.compile(r"^[a-z_][a-z0-9_]*\.(py|md)$")
_PHASE0_ALLOWED = ("COMMIT", "WAIT", "REFUSE")


def _canon(value) -> str:
    """Flow-slot canonicalization (§7.1): case-fold, strip quotes/space."""
    return str(value).strip().strip("'\"").strip().lower()


def validate(state: State, seat: str, action) -> str | None:
    sc = state.scenario
    p = sc.params
    name, args = action.name, action.args

    if state.over:
        return "the episode is over"
    if seat != state.mover:
        return f"it is {state.mover}'s move"

    if state.phase0 and name not in _PHASE0_ALLOWED:
        return "the build has not opened"

    if p.comms_off and name in ("QUERY", "INFORM", "PROPOSE_IFACE", "AGREE"):
        return "communication is disabled in this episode"

    if name == "COMMIT":
        if not state.phase0:
            return "COMMIT is legal only in the silent round (turns 1-3)"
        if state.committed(seat):
            return "you have already committed"
        slots = args.get("slots")
        if not isinstance(slots, dict) or not slots:
            return "COMMIT needs slots: {slot_id -> value}"
        opening = [s for s in sc.slots
                   if s.kind == "menu" and not s.addendum]
        want = {s.slot_id for s in opening}
        if set(slots) != want:
            return f"commit exactly the opening menu slots: {sorted(want)}"
        for sid, value in slots.items():
            slot = sc.slot(sid)
            if value not in slot.menu:
                return (f"slot {sid} accepts one of {list(slot.menu)}")
        return None

    if name == "READ":
        path = args.get("path")
        if path not in state.workspace:
            return f"no file named {path!r}"
        return None

    if name == "WRITE":
        path = args.get("path")
        if not isinstance(path, str) or not _PATH_RE.match(path or ""):
            return "path must be a flat lowercase .py or .md filename"
        if path in ENGINE_ARTIFACTS:
            return f"{path} is an engine artifact and cannot be written"
        content = args.get("content")
        if not isinstance(content, str):
            return "content must be a string"
        if len(content.split("\n")) > p.lines_max:
            return f"files are capped at {p.lines_max} lines"
        if path not in state.workspace and len(state.workspace) >= p.files_max:
            return f"the workspace is capped at {p.files_max} files"
        return None

    if name == "RUN":
        if state.runs_left <= 0:
            return "the run budget is exhausted"
        return None

    if name == "PROBE":
        if seat != "QA":
            return "only QA can probe the hidden suite"
        if state.probes_left <= 0:
            return "the probe budget is exhausted"
        tid = args.get("test_id")
        known = {h.test_id for h in sc.hidden
                 if state.amended or not h.addendum}
        if tid not in known:
            return f"unknown hidden test id {tid!r}"
        return None

    if name == "RELEASE":
        if state.tokens_left <= 0:
            return "no release tokens remain"
        return None

    if name == "PROPOSE_IFACE":
        c = args.get("contract")
        if not isinstance(c, dict):
            return "PROPOSE_IFACE needs a contract object"
        parties = c.get("parties") or []
        if not (2 <= len(parties) <= 3) or len(set(parties)) != len(parties) \
                or any(q not in SEATS for q in parties):
            return "parties must name 2 or 3 distinct seats"
        if seat not in parties:
            return "the proposer must be a named party"
        binds = c.get("binds", [])
        obliges = c.get("obliges", [])
        if len(binds) > p.contract_slots_max:
            return f"a contract binds at most {p.contract_slots_max} slots"
        if len(obliges) > p.contract_obliges_max:
            return f"a contract carries at most {p.contract_obliges_max} obligations"
        if not binds and not obliges:
            return "a contract must bind a slot or oblige a task"
        active = {s.slot_id: s for s in sc.active_slots(state.amended)}
        for b in binds:
            sid = b.get("slot_id")
            if sid not in active:
                return f"no slot named {sid!r}"
            slot = active[sid]
            value = b.get("value")
            if slot.kind == "menu":
                if value not in slot.menu:
                    return f"slot {sid} accepts one of {list(slot.menu)}"
            else:
                if not _canon(value):
                    return f"slot {sid} needs a non-empty value"
        tasks = {t.task_id for t in sc.tasks if state.amended or not t.addendum}
        for ob in obliges:
            if ob.get("seat") not in parties:
                return "every obliged seat must be a named party"
            if ob.get("task_id") not in tasks:
                return f"no task named {ob.get('task_id')!r}"
            by = ob.get("by")
            if by is not None:
                if not isinstance(by, int) or not (state.tick + 1 < by <= p.D):
                    return (f"'by' must satisfy turn < by <= {p.D}")
        return None

    if name == "AGREE":
        cid = args.get("contract_id")
        try:
            c = state.contracts[int(cid)]
        except (KeyError, TypeError, ValueError):
            return f"no contract {cid!r}"
        if c.locked:
            return f"contract {c.cid} is already locked"
        if not c.is_offer_live(state.tick + 1):
            return f"contract {c.cid} has lapsed"
        if seat not in c.parties:
            return "you are not a named party"
        if seat == c.proposer:
            return "the proposer's standing is implicit; nothing to agree"
        if seat in c.agreed_by:
            return "you have already agreed"
        return None

    if name == "REPORT":
        claims = args.get("claims")
        if not isinstance(claims, list) or not (1 <= len(claims) <= p.report_claims_max):
            return f"REPORT carries 1 to {p.report_claims_max} claims"
        public = {t.test_id for t in sc.public}
        tasks = {t.task_id for t in sc.tasks if state.amended or not t.addendum}
        for cl in claims:
            if not isinstance(cl, dict):
                return "each claim is {scope, verdict}"
            scope, verdict = cl.get("scope"), cl.get("verdict")
            if verdict not in ("pass", "fail", "done"):
                return "verdict must be pass, fail, or done"
            if scope == "all-public":
                continue
            if isinstance(scope, str) and scope in public:
                continue
            if isinstance(scope, dict) and scope.get("task_id") in tasks \
                    and isinstance(scope.get("path"), str):
                continue
            return f"claim scope {scope!r} is not a public test id, " \
                   "'all-public', or {path, task_id}"
        return None

    if name in ("QUERY", "INFORM"):
        to = args.get("to")
        if to not in SEATS or to == seat:
            return "'to' must name one of your two teammates"
        if not isinstance(args.get("text"), str) or not args["text"].strip():
            return "text must be a non-empty string"
        return None

    if name in ("WAIT", "REFUSE"):
        return None

    return f"unknown action {name!r}"
