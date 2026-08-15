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

import itertools
import json

from ..core import actions as actions_mod
from ..core.events import ACTIONS, Action
from ..core.events import SEATS
from ..core.fold import HOME_ARTIFACT, State, set_slot_literal
from ..core.scenario import ENGINE_ARTIFACTS
from ..grading.reports import grade_report
from ..grading.suite import hidden_score
from ..slots.extract import extract

RELEASE_DELTA = 3

OMEGA1_VOCABULARY: tuple[str, ...] = ACTIONS

_WRITE_TOKENS = tuple(
    f"WRITE:{owner}:{status}{flip}"
    for owner in ("own", "cross")
    for status in ("consistent", "breach")
    for flip in ("", ":flip-self", ":flip-away")
)
OMEGA2_VOCABULARY: tuple[str, ...] = (
    ("COMMIT",)
    + ("READ:own", "READ:cross")
    + _WRITE_TOKENS
    + ("RUN", "PROBE")
    + tuple(f"RELEASE:{tone}" for tone in ("improving", "degrading", "neutral"))
    + ("PROPOSE_IFACE:b0:unloaded",)
    + tuple(
        f"PROPOSE_IFACE:b{width}:{side}"
        for width in (1, 2)
        for side in ("self", "other", "unloaded")
    )
    + tuple(f"AGREE:{side}" for side in ("self", "other", "unloaded"))
    + ("REPORT:true", "REPORT:false")
    + tuple(
        f"{name}:{recipient}"
        for name in ("QUERY", "INFORM")
        for recipient in ("to-x", "to-y")
    )
    + ("WAIT", "REFUSE")
)


def focality_token(action: Action) -> str:
    """Opening-commitment token; unlike Omega-2, preserves chosen values."""
    if action.name != "COMMIT":
        return action.name
    return "COMMIT:" + json.dumps(
        dict(action.args.get("slots", {})),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def legal_focality_alphabet(state: State, seat: str) -> list[str]:
    """Finite legal alphabet for an opening convention decision."""
    if state.over or seat != state.mover or not state.phase0:
        return []
    slots = [
        slot for slot in state.scenario.slots
        if slot.kind == "menu" and not slot.addendum
    ]
    tokens = []
    for values in itertools.product(*(slot.menu for slot in slots)):
        action = Action("COMMIT", {
            "slots": {
                slot.slot_id: value
                for slot, value in zip(slots, values, strict=True)
            }
        })
        if actions_mod.validate(state, seat, action) is None:
            tokens.append(focality_token(action))
    for name in ("WAIT", "REFUSE"):
        action = Action(name, {})
        if actions_mod.validate(state, seat, action) is None:
            tokens.append(name)
    return tokens


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


def _candidate_actions(state: State, seat: str) -> dict[str, list[Action]]:
    """Construct witnesses for every action label that can be legal here.

    This does not enumerate argument values.  It only asks whether a label has
    at least one legal instantiation at the frozen state, after which the
    registered refinement vocabulary supplies every outcome for that label.
    """
    sc = state.scenario
    others = [s for s in SEATS if s != seat]
    candidates: dict[str, list[Action]] = {name: [] for name in ACTIONS}

    opening = [s for s in sc.slots if s.kind == "menu" and not s.addendum]
    if opening:
        candidates["COMMIT"].append(Action(
            "COMMIT", {"slots": {s.slot_id: s.menu[0] for s in opening}}))

    for path in sorted(state.workspace):
        candidates["READ"].append(Action("READ", {"path": path}))
    writable = [p for p in sorted(state.workspace) if p not in ENGINE_ARTIFACTS]
    if writable:
        path = writable[0]
        candidates["WRITE"].append(
            Action("WRITE", {"path": path, "content": state.workspace[path]}))

    candidates["RUN"].append(Action("RUN", {}))
    for test in sc.hidden:
        if state.amended or not test.addendum:
            candidates["PROBE"].append(Action("PROBE", {"test_id": test.test_id}))
    candidates["RELEASE"].append(Action("RELEASE", {}))

    active = list(sc.active_slots(state.amended))
    contract: dict = {"parties": [seat, others[0]], "binds": [], "obliges": []}
    if active:
        slot = active[0]
        if slot.kind == "menu":
            value = slot.menu[0]
        else:
            value = slot.prefs.get(seat) or next(iter(slot.prefs.values()), "value")
        contract["binds"] = [{"slot_id": slot.slot_id, "value": value}]
    else:
        tasks = [t for t in sc.tasks if state.amended or not t.addendum]
        if tasks:
            contract["obliges"] = [
                {"seat": seat, "task_id": tasks[0].task_id, "by": None}
            ]
    if contract["binds"] or contract["obliges"]:
        candidates["PROPOSE_IFACE"].append(
            Action("PROPOSE_IFACE", {"contract": contract}))

    for cid in sorted(state.contracts):
        candidates["AGREE"].append(Action("AGREE", {"contract_id": cid}))

    if sc.public:
        candidates["REPORT"].append(Action(
            "REPORT", {"claims": [{"scope": sc.public[0].test_id, "verdict": "pass"}]}))
    for other in others:
        candidates["QUERY"].append(Action("QUERY", {"to": other, "text": "status"}))
        candidates["INFORM"].append(Action("INFORM", {"to": other, "text": "status"}))
    candidates["WAIT"].append(Action("WAIT", {}))
    candidates["REFUSE"].append(Action("REFUSE", {}))
    return candidates


def legal_omega1_alphabet(state: State, seat: str) -> list[str]:
    """Action labels with at least one legal instantiation at this decision."""
    if state.over or seat != state.mover:
        return []
    candidates = _candidate_actions(state, seat)
    legal = {
        name
        for name, actions in candidates.items()
        if any(actions_mod.validate(state, seat, action) is None for action in actions)
    }
    return [name for name in OMEGA1_VOCABULARY if name in legal]


def legal_omega2_alphabet(state: State, seat: str) -> list[str]:
    """Omega-2 outcomes reachable by at least one legal action here.

    Labels are not enough for FORGE: RELEASE has one deterministic refinement,
    AGREE depends on the referenced contract, and b0 can only be `unloaded`.
    We therefore enumerate finite witnesses for every refinement.  WRITE has
    unbounded text arguments, but its token depends only on anchored slot
    literals; enumerating current, bound, preferred, and sentinel literals is
    exhaustive for that finite token partition.
    """
    labels = set(legal_omega1_alphabet(state, seat))
    if not labels:
        return []
    sc = state.scenario
    tokens: set[str] = set()

    # Label-only actions and deterministic refinements.
    for name in labels & {"COMMIT", "RUN", "PROBE", "WAIT", "REFUSE"}:
        tokens.add(name)
    if "RELEASE" in labels:
        tokens.add(omega2(sc, state, seat, Action("RELEASE", {})))

    if "READ" in labels:
        for path in sorted(state.workspace):
            action = Action("READ", {"path": path})
            if actions_mod.validate(state, seat, action) is None:
                tokens.add(omega2(sc, state, seat, action))

    if "WRITE" in labels:
        for path in sorted(p for p in state.workspace if p not in ENGINE_ARTIFACTS):
            slots = [slot for slot in sc.active_slots(state.amended) if path in slot.artifacts]
            choices = []
            for slot in slots:
                # A legal WRITE may remove the anchored literal altogether.
                # That maps to bottom (None) and can be the only witness for a
                # no-flip, non-breach token when the current value is loaded
                # and a different value is contract-bound.
                values = {extract(state.workspace, slot, path), "", "__omega_other__"}
                bound = state.current_binding(slot.slot_id)
                if bound is not None:
                    values.add(bound[2])
                values.update(slot.prefs.values())
                if slot.kind == "menu":
                    values.update(slot.menu)
                choices.append(sorted(str(value) for value in values if value is not None))
            assignments = {()}
            for index, values in enumerate(choices):
                assignments.update(((index, value),) for value in values)
            # Two changed literals suffice for this token partition: one can
            # determine the first loaded-slot flip and one can independently
            # determine whether any locked binding is breached.
            for first, second in itertools.combinations(range(len(choices)), 2):
                assignments.update(
                    ((first, left), (second, right))
                    for left in choices[first] for right in choices[second]
                )
            for assignment in assignments:
                content = state.workspace[path]
                for index, value in assignment:
                    slot = slots[index]
                    content = set_slot_literal(content, slot.const_name, value)
                action = Action("WRITE", {"path": path, "content": content})
                if actions_mod.validate(state, seat, action) is None:
                    tokens.add(omega2(sc, state, seat, action))

    if "REPORT" in labels:
        for test in sc.public:
            for verdict in ("pass", "fail", "done"):
                action = Action("REPORT", {
                    "claims": [{"scope": test.test_id, "verdict": verdict}]
                })
                if actions_mod.validate(state, seat, action) is None:
                    tokens.add(omega2(sc, state, seat, action))

    if labels & {"QUERY", "INFORM"}:
        for name in labels & {"QUERY", "INFORM"}:
            for other in (value for value in SEATS if value != seat):
                action = Action(name, {"to": other, "text": "status"})
                if actions_mod.validate(state, seat, action) is None:
                    tokens.add(omega2(sc, state, seat, action))

    if "AGREE" in labels:
        for cid in sorted(state.contracts):
            action = Action("AGREE", {"contract_id": cid})
            if actions_mod.validate(state, seat, action) is None:
                tokens.add(omega2(sc, state, seat, action))

    if "PROPOSE_IFACE" in labels:
        others = [value for value in SEATS if value != seat]
        party_sets = ([seat, others[0]], [seat, others[1]], [seat, *others])
        active = list(sc.active_slots(state.amended))
        tasks = [task for task in sc.tasks if state.amended or not task.addendum]
        if tasks:
            contract = {
                "parties": party_sets[0], "binds": [],
                "obliges": [{"seat": seat, "task_id": tasks[0].task_id, "by": None}],
            }
            action = Action("PROPOSE_IFACE", {"contract": contract})
            if actions_mod.validate(state, seat, action) is None:
                tokens.add(omega2(sc, state, seat, action))
        for width in (1, 2):
            for slots in itertools.combinations(active, width):
                value_sets = []
                for slot in slots:
                    values = set(slot.menu) if slot.kind == "menu" else set(slot.prefs.values())
                    values.add("__omega_other__")
                    value_sets.append(sorted(values))
                for values in itertools.product(*value_sets):
                    binds = [{"slot_id": slot.slot_id, "value": value}
                             for slot, value in zip(slots, values)]
                    for parties in party_sets:
                        action = Action("PROPOSE_IFACE", {"contract": {
                            "parties": parties, "binds": binds, "obliges": [],
                        }})
                        if actions_mod.validate(state, seat, action) is None:
                            tokens.add(omega2(sc, state, seat, action))

    unknown = tokens - set(OMEGA2_VOCABULARY)
    if unknown:
        raise RuntimeError(f"reachable Omega-2 tokens are absent from vocabulary: {sorted(unknown)}")
    return [token for token in OMEGA2_VOCABULARY if token in tokens]
