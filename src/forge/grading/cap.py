"""Cap(I), Head, and the score decomposition (§6.2, §6.3).

Cap(I) = W_pub + Σ w(h) over fragment tests with R(h) ⊆ I + W_match.
Matching weight is information-free and therefore inside every ceiling.
"""
from __future__ import annotations

from ..core.scenario import Scenario

SEAT_KEYS = {"API": "A", "DATA": "D", "QA": "Q"}


def cap(sc: Scenario, info: frozenset) -> int:
    total = 0
    for h in sc.hidden:
        if h.kind == "matching" or h.kind == "public":
            total += h.weight
        elif set(h.req) <= set(info):
            total += h.weight
    return total


def head(sc: Scenario) -> int:
    full = cap(sc, frozenset(("API", "DATA", "QA")))
    best_single = max(cap(sc, frozenset((s,))) for s in ("API", "DATA", "QA"))
    return full - best_single


def components(sc: Scenario) -> dict:
    """The §6.3 table recomputed from the suite, for tests and reporting."""
    out: dict = {}
    for h in sc.hidden:
        if h.kind == "public":
            key = "public"
        elif h.kind == "matching":
            key = "matching"
        else:
            key = "+".join(sorted(SEAT_KEYS[s] for s in h.req))
        out[key] = out.get(key, 0) + h.weight
    return out
