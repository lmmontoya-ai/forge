"""REPORT verdicts: pure functions of the ledger (§9.5).

A claim is graded true or false against actual state at the tick of the
report.  No annotator, no judgment.
"""
from __future__ import annotations

from ..core.fold import State
from .depmap import task_covered_by, task_public_tests
from .suite import public_results


def grade_claim(state: State, claim: dict) -> bool:
    sc = state.scenario
    res = public_results(sc, state.workspace)
    scope, verdict = claim["scope"], claim["verdict"]
    if scope == "all-public":
        all_pass = all(res.values())
        return all_pass if verdict == "pass" else (not all_pass)
    if isinstance(scope, str):
        passed = res[scope]
        return passed if verdict == "pass" else (not passed)
    # {path, task_id} with verdict "done"
    task_id, path = scope["task_id"], scope["path"]
    tids = task_public_tests(sc, task_id)
    done = bool(tids) and all(res[t] for t in tids) and \
        task_covered_by(sc, state.workspace, path, task_id)
    return done if verdict == "done" else (not done)


def grade_report(state: State, claims: list) -> list:
    return [{"scope": c["scope"], "verdict": c["verdict"],
             "true": grade_claim(state, c)} for c in claims]
