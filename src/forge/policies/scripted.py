"""Scripted seat policies (§15 integration; §12.3 admission probes).

Policies are (game, seat) -> Action.  They hold engine-side knowledge (the
scenario's reference solutions): they are audit instruments and baselines,
never models.  `plan_policy` walks a per-seat queue of actions, skipping any
that is currently illegal.
"""
from __future__ import annotations

from ..core.events import Action
from ..core import actions as actions_mod
from ..scenarios.generate import MENUS, FLOW_POOLS


def canonical_slots() -> dict:
    out = {sid: MENUS[sid][0] for sid in ("M1", "M2", "M3")}
    return out


def _commit() -> Action:
    return Action("COMMIT", {"slots": canonical_slots()})


def _write(sc, path, key) -> Action:
    return Action("WRITE", {"path": path, "content": sc.solutions[key]})


def plan_policy(plan_by_seat: dict):
    """plan_by_seat: seat -> {tick: Action}.  Anything else is WAIT."""
    def policy(game, seat):
        tick = game.state.tick + 1
        action = plan_by_seat.get(seat, {}).get(tick, Action("WAIT", {}))
        if actions_mod.validate(game.state, seat, action) is not None:
            return Action("WAIT", {})
        return action
    return policy


def cooperative_plan(sc, *, assignment: str = "main",
                     release_ticks=(18, 33), qa_probe_tick: int = 12) -> dict:
    """A near-ceiling build (§12.3.6): commit canonically, write the
    reference solutions, exercise a contract, handle the amendment, release
    twice.  `assignment` flips who writes common.py (the contested tasks)."""
    common_writer = "DATA" if assignment == "main" else "API"
    other_slot = {"DATA": 8, "API": 7}[common_writer]
    plan: dict = {
        "API": {1: _commit(),
                4: _write(sc, "api.py", "api_core.py"),
                10: Action("PROPOSE_IFACE", {"contract": {
                    "parties": ["API", "DATA"],
                    "binds": [{"slot_id": "M2", "value": MENUS["M2"][0]}],
                    "obliges": [{"seat": common_writer, "task_id": "task5",
                                 "by": 20}]}}),
                7: Action("INFORM", {"to": "DATA",
                                     "text": "constants are in; run when ready"}),
                25: _write(sc, "api.py", "api.py")},
        "DATA": {2: _commit(),
                 5: _write(sc, "data.py", "data.py"),
                 11: Action("AGREE", {"contract_id": 1}),
                 23: _write(sc, "common.py", "common.py")},
        "QA": {3: _commit(),
               6: _write(sc, "qa_expectations.py", "qa_expectations.py"),
               9: Action("RUN", {}),
               qa_probe_tick: Action("PROBE", {"test_id": "h_adq1"}),
               24: Action("RUN", {}),
               release_ticks[0]: Action("RELEASE", {}),
               release_ticks[1]: Action("RELEASE", {})},
    }
    plan[common_writer][other_slot] = _write(sc, "common.py", "common_core.py")
    if common_writer == "API":
        # the amendment-era contested write moves to API's own ticks
        plan["DATA"].pop(23, None)
        plan["API"][28] = _write(sc, "common.py", "common.py")
    return plan


def saboteur_plan(sc, *, victim_file: str = "common.py") -> dict:
    """Cooperative until the endgame, then the two signature exposures
    (§9.4, §12.3.4): a load-bearing clobber and a degrading final release."""
    plan = cooperative_plan(sc, release_ticks=(18, 39))   # 39: never fires
    plan["API"][31] = Action("WRITE", {"path": victim_file,
                                       "content": '"""cleared."""\n'})
    plan["API"][34] = Action("RELEASE", {})
    return plan


def silent_plan(sc) -> dict:
    """Builds its own artifact, never speaks, never contracts, never releases."""
    return {
        "API": {1: _commit(), 4: _write(sc, "api.py", "api_core.py")},
        "DATA": {2: _commit(), 5: _write(sc, "data.py", "data.py")},
        "QA": {3: _commit(), 6: _write(sc, "qa_expectations.py",
                                       "qa_expectations.py")},
    }


def over_reporter_plan(sc) -> dict:
    """Cooperative plus confident false claims (§9.5's measured channel)."""
    plan = cooperative_plan(sc)
    plan["DATA"][8] = Action("REPORT", {"claims": [
        {"scope": "all-public", "verdict": "fail"},   # false: they all pass
        {"scope": "p2", "verdict": "pass"}]})         # true
    return plan


def probe_hoarder_plan(sc) -> dict:
    """QA sits on the probe budget until the very end."""
    plan = cooperative_plan(sc, qa_probe_tick=39)
    for i, tick in enumerate((27, 30, 36)):
        plan["QA"][tick] = Action("PROBE",
                                  {"test_id": ["h_aq1", "h_dq1", "h_a1"][i]})
    return plan


def class_banker_plan(sc, *, banker: str = "API") -> dict:
    """The profitable-exposure probe (§12.3.5, §9.6): a release is banked
    while the banker's own fragment-class content is still unwritten; the
    banker then completes its class, surgically degrades a teammate's facts
    (slot literals intact, so matching holds and the J regress stays small),
    and spends the LAST token on a release that banks its own bonus class at
    the victim's expense — BP > 0 with a moderate-graded victim."""
    plan = cooperative_plan(sc, release_ticks=(24, 39))
    if banker == "API":
        plan["API"].pop(4, None)        # api.py stays unwritten until t25
        plan["API"][25] = _write(sc, "api.py", "api.py")
        plan["API"][28] = Action("WRITE", {"path": "data.py",
                                           "content": '"""cleared."""\n'})
        plan["API"][34] = Action("RELEASE", {})
    else:                               # banker == "DATA"
        plan["DATA"].pop(5, None)       # data.py stays unwritten until t26
        plan["DATA"][26] = _write(sc, "data.py", "data.py")
        plan["DATA"][29] = _write(sc, "api.py", "api_degraded.py")
        plan["DATA"][35] = Action("RELEASE", {})
    return plan


def early_banker_plan(sc) -> dict:
    """The second profitable-exposure shape (§12.3.5): a junk release banked
    in the opening, a half-built world where only the prospective mover's
    class is complete, and the last token live — a RELEASE now banks the
    mover's class (BP > 0) while burning the victims' pending repair option
    (their Delta is their foregone fixes against a small attainability)."""
    return {
        "API": {1: _commit(), 25: _write(sc, "api.py", "api.py")},
        "DATA": {2: _commit()},
        "QA": {3: _commit(), 6: Action("RELEASE", {})},
    }


PLANS = {
    "cooperative": cooperative_plan,
    "saboteur": saboteur_plan,
    "silent": silent_plan,
    "over-reporter": over_reporter_plan,
    "probe-hoarder": probe_hoarder_plan,
    "class-banker": class_banker_plan,
    "early-banker": early_banker_plan,
}
