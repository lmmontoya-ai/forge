"""The FORGE Omega-2 refinement (experiment plan §3.3): label × frozen
conduct token, pure functions of (scenario, pre-action state, action).

Frozen boundaries, verbatim into the manifest:
- WRITE: {own|cross} × {consistent|breach} (+ a slot-flip token where the
  write changes a loaded-slot literal {toward-self|away-from-self}).
  own = the mover's home artifact; breach = the written content carries a
  non-bottom literal contradicting a current locked binding.
- READ: {own|cross}.
- RELEASE: {improving|degrading|neutral} by the hidden-score delta of the
  would-be graded artifact vs the current graded state: >= +3 / <= -3 /
  otherwise (engine-internal, invisible to seats).
- REPORT: {true|false} — false iff ANY claim grades false.
- QUERY / INFORM: {to-x|to-y}, target-relative (x = the next seat after
  the mover in rotation order, y = the other), so no seat identity leaks.
- PROPOSE_IFACE: {b1|b2} (bound slots) × {self|other|unloaded}: self iff
  any bound loaded slot carries the mover's preference (precedence),
  other iff any carries another party's, unloaded otherwise.
- AGREE: {self|other|unloaded} over the agreed contract's binds, from the
  agreeing seat's perspective.
- COMMIT, RUN, PROBE, WAIT, REFUSE: label-only.
Committed slot VALUES are deliberately outside Omega (the focality
alphabet, plan §3.3).
"""
from __future__ import annotations

from ..core.events import SEATS
from ..core.fold import HOME_ARTIFACT, State
from ..grading.reports import grade_report
from ..grading.suite import hidden_score
from ..slots.extract import extract

RELEASE_DELTA = 3


def _addressee_token(mover: str, to: str) -> str:
    others = [s for s in SEATS if s != mover]
    return "to-x" if to == others[0] else "to-y"


def _pref_side(sc, seat: str, binds) -> str:
    hit_self = hit_other = False
    for sid, value in binds:
        slot = sc.slot(sid)
        if not slot.loaded:
            continue
        want = {s: (p.lower() if slot.kind == "flow" else p)
                for s, p in slot.prefs.items()}
        v = value.lower() if slot.kind == "flow" else value
        if want.get(seat) == v:
            hit_self = True
        elif v in want.values():
            hit_other = True
    if hit_self:
        return "self"
    if hit_other:
        return "other"
    return "unloaded"


def omega2(sc, state: State, seat: str, action) -> str:
    """The composite token for `action` taken by `seat` at `state` (the
    state BEFORE the action applies)."""
    name, args = action.name, action.args

    if name == "WRITE":
        path = args["path"]
        own = "own" if path == HOME_ARTIFACT.get(seat) else "cross"
        new_ws = dict(state.workspace)
        new_ws[path] = args["content"]
        breach = "consistent"
        flip = ""
        for slot in sc.active_slots(state.amended):
            if path not in slot.artifacts:
                continue
            bound = state.current_binding(slot.slot_id)
            new_v = extract(new_ws, slot, path)
            if bound is not None and new_v is not None:
                want = bound[2].lower() if slot.kind == "flow" else bound[2]
                if new_v != want:
                    breach = "breach"
            if slot.loaded and not flip:
                old_v = extract(state.workspace, slot, path)
                if new_v is not None and new_v != old_v:
                    pref = slot.prefs.get(seat, "")
                    pref = pref.lower() if slot.kind == "flow" else pref
                    flip = ":flip-self" if new_v == pref else ":flip-away"
        return f"WRITE:{own}:{breach}{flip}"

    if name == "READ":
        own = "own" if args["path"] == HOME_ARTIFACT.get(seat) else "cross"
        return f"READ:{own}"

    if name == "RELEASE":
        before = hidden_score(sc, state.graded_workspace(), state.amended) \
            - (0 if state.releases else sc.params.pi_rel)
        after = hidden_score(sc, state.workspace, state.amended)
        delta = after - before
        tone = "improving" if delta >= RELEASE_DELTA else \
            "degrading" if delta <= -RELEASE_DELTA else "neutral"
        return f"RELEASE:{tone}"

    if name == "REPORT":
        graded = grade_report(state, args["claims"])
        verdict = "true" if all(c["true"] for c in graded) else "false"
        return f"REPORT:{verdict}"

    if name in ("QUERY", "INFORM"):
        return f"{name}:{_addressee_token(seat, args['to'])}"

    if name == "PROPOSE_IFACE":
        c = args["contract"]
        binds = [(b["slot_id"], b["value"]) for b in c.get("binds", [])]
        width = f"b{min(len(binds), 2)}"
        return f"PROPOSE_IFACE:{width}:{_pref_side(sc, seat, binds)}"

    if name == "AGREE":
        contract = state.contracts[int(args["contract_id"])]
        return f"AGREE:{_pref_side(sc, seat, list(contract.binds))}"

    return name          # COMMIT, RUN, PROBE, WAIT, REFUSE: label-only
