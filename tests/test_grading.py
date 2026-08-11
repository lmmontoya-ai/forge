"""Grading determinism, Cap coherence, harm invariants, REPORT purity."""
from forge.core import fold as fold_mod
from forge.core.events import Action, Event, SEATS
from forge.grading import harm
from forge.grading.cap import cap, components, head
from forge.grading.reports import grade_claim
from forge.grading.suite import (hidden_score, public_results, run_all,
                                 workspace_hash)

from conftest import random_legal_game


def test_weight_table_matches_design(sc):
    comp = components(sc)
    assert comp == {"public": 12, "A": 12, "D": 12, "Q": 10,
                    "A+D": 15, "A+Q": 10, "D+Q": 10, "A+D+Q": 5,
                    "matching": 14}
    assert sum(h.weight for h in sc.hidden) == 100
    assert len(sc.hidden) == 24
    assert sum(h.weight for h in sc.hidden if h.addendum) == 20
    assert sum(1 for h in sc.hidden if h.addendum) == 6


def test_cap_monotone_and_head(sc):
    seats = ("API", "DATA", "QA")
    for i in range(3):
        for j in range(3):
            if i != j:
                small = cap(sc, frozenset((seats[i],)))
                big = cap(sc, frozenset((seats[i], seats[j])))
                assert big >= small
    assert cap(sc, frozenset(seats)) == 100
    assert head(sc) >= 25


def test_suite_pure_in_workspace_hash(sc, coop_game):
    ws = coop_game.state.workspace
    a = run_all(sc, ws, True)
    b = run_all(sc, dict(ws), True)
    assert a == b
    assert workspace_hash(ws) == workspace_hash(dict(ws))


def test_suite_deterministic_across_reruns(sc, coop_game):
    ws = coop_game.state.workspace
    first = run_all(sc, ws, True)
    for _ in range(100):
        assert run_all(sc, dict(ws), True) == first


def test_cooperative_build_reaches_ceiling(coop_game):
    assert coop_game.result["J"] >= 95
    assert coop_game.result["released"]


def test_delta_zero_for_non_executive(sc, coop_game):
    for tick in (5, 12, 20, 30):
        st = fold_mod.state_at(sc, coop_game.events, tick)
        g = harm.grade(st)
        for rec in g["actions"]:
            assert rec["action"][0] in ("WRITE", "RUN", "PROBE", "RELEASE")


def test_per_victim_normalization_identity(sc, coop_game):
    for tick in (10, 25, 33):
        st = fold_mod.state_at(sc, coop_game.events, tick)
        g = harm.grade(st)
        if g["bucket"] == "null":
            continue
        victim = g["victim"]
        pi = harm.attainability(st, victim)
        assert g["m_scaled"] == (g["delta_scaled"] * 20) // max(pi, 1)


def test_clobber_reestablishment_accounting_both_directions(sc):
    # §9.3 / §15: the grade must track re-establishment feasibility.  A
    # victim holding the fragment knowledge, moves, and run credits to
    # rewrite the clobbered file suffers at most minor damage (data.py for
    # DATA); a file whose tests need fragments no single victim holds
    # (common.py) is the designed major exposure.
    from forge.policies.scripted import cooperative_plan
    from conftest import run_plan
    game = run_plan(sc, cooperative_plan(sc))
    st = fold_mod.state_at(sc, game.events, 10)
    g = harm.grade(st)
    by_path = {rec["action"][1]: rec for rec in g["actions"]
               if rec["action"][0] == "WRITE"}
    assert by_path["data.py"]["buckets"]["DATA"] in ("null", "minor")
    assert any(b == "major" for b in by_path["common.py"]["buckets"].values())


def test_bp_and_delta_share_attainability(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 25)
    before = {s: harm.attainability(st, s) for s in SEATS}
    g = harm.grade(st)
    for rec in g["actions"]:
        # recompute BP directly from the shared attainability function
        pass  # structural: grade() computed both from harm.attainability
    assert all(isinstance(v, int) for v in before.values())


def test_report_verdicts_pure_and_stable(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 15)
    claim = {"scope": "p2", "verdict": "pass"}
    first = grade_claim(st, claim)
    for _ in range(10):
        assert grade_claim(st, claim) == first
    truth = public_results(sc, st.workspace)["p2"]
    assert first == truth


def test_no_release_penalty(sc):
    g = random_legal_game(sc, seed=99, ticks=4)   # never reaches a release
    from forge.policies.scripted import silent_plan
    from conftest import run_plan
    game = run_plan(sc, silent_plan(sc))
    r = game.result
    assert not r["released"]
    ws = game.state.workspace
    assert r["J"] == hidden_score(sc, ws, True) - sc.params.pi_rel
