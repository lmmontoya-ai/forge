"""Breach detection: a pure function of the ledger (design §5).

A locked contract is violated the moment any artifact's extracted slot
value contradicts a bound value (non-bottom mismatch), or an obliged task's
deadline passes unimplemented.  Latest lock wins per slot and per task.
"""
from __future__ import annotations

from ..core.fold import State
from ..grading.depmap import task_public_tests
from ..grading.suite import public_results
from ..slots.extract import extract


def breaches(state: State) -> list:
    sc = state.scenario
    out = []
    seen_slots = {}
    for c in state.contracts.values():
        if not c.locked:
            continue
        for sid, value in c.binds:
            cur = state.current_binding(sid)
            if cur is None or cur[1] != c.cid:
                continue                      # superseded by a later lock
            slot = sc.slot(sid)
            want = value.lower() if slot.kind == "flow" else value
            for path in slot.artifacts:
                got = extract(state.workspace, slot, path)
                if got is not None and got != want:
                    out.append({"cid": c.cid, "kind": "slot", "slot": sid,
                                "path": path, "bound": want, "found": got})
    obligations = state.current_obligations()
    res = None
    for task_id, (_, cid, seat, by) in obligations.items():
        if by is None or state.tick < by:
            continue
        if res is None:
            res = public_results(sc, state.workspace)
        tids = task_public_tests(sc, task_id)
        if not tids or not all(res[t] for t in tids):
            out.append({"cid": cid, "kind": "obligation", "task": task_id,
                        "seat": seat, "by": by})
    return out
