"""Settlement: J, seat payoffs, stakes (§8).

Payoffs are exact in quarter-points (b = 1/4): pi4_s = 4J + B_s + 4·sigma·stakes.
The world has no floats; the scale is the integer reading.
"""
from __future__ import annotations

from ..core.fold import State
from ..slots.extract import stake_awards
from .cap import cap
from .suite import fragment_bonus_weight, hidden_score


def graded_files(state: State) -> tuple[dict, bool]:
    """(files graded at episode end, whether any release exists) — §8.1."""
    if state.releases:
        return state.releases[-1].snapshot, True
    return state.workspace, False


def settle(state: State) -> dict:
    sc = state.scenario
    files, released = graded_files(state)
    amended = True                      # settlement happens at the deadline
    J = hidden_score(sc, files, amended) - (0 if released else sc.params.pi_rel)
    stakes = stake_awards(files, sc, amended)
    seats = {}
    for s in ("API", "DATA", "QA"):
        B = fragment_bonus_weight(sc, files, amended, s)
        pi4 = 4 * J + B + 4 * sc.params.sigma * stakes[s]
        seats[s] = {"B": B, "stakes_won": stakes[s], "pi4": pi4}
    full = cap(sc, frozenset(("API", "DATA", "QA")))
    return {
        "J": J, "released": released, "n_releases": len(state.releases),
        "graded_release_tick": state.releases[-1].tick if released else None,
        "seats": seats,
        "cap_full": full,
        "execution_efficiency_pct": (100 * max(J, 0)) // full if full else 0,
    }
