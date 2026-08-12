"""The F-A resolution's frozen relationships (design §9.6 as revised).

1. One settle-now valuation: Pi_att(seat) == banked_value(seat) + g(seat);
   the mover's premium side is the banked projection, the victim's side is
   banked plus g.
2. The no-op guard: premium-versus-WAIT is identically the net premium —
   stepping the ledger by a WAIT changes no seat's banked value and, with
   the mover's imminent move excluded from its own 'before', no seat's g.
3. Temptation premium of WAIT is zero everywhere.
"""
from dataclasses import replace

from forge.core import fold as fold_mod
from forge.core.events import SEATS
from forge.grading import harm


def _decision_states(sc, events, ticks):
    for tick in ticks:
        st = fold_mod.state_at(sc, events, tick)
        if not st.phase0 and not st.over:
            yield st


def test_single_valuation_identity(sc, coop_game):
    for st in _decision_states(sc, coop_game.events, (5, 11, 19, 25, 31)):
        for seat in SEATS:
            assert harm.attainability(st, seat) == \
                harm.banked_value(st, seat) + harm.reachable_gain(st, seat)


def test_wait_is_a_noop_for_both_premia(sc, coop_game):
    for st in _decision_states(sc, coop_game.events, (5, 11, 19, 25, 31, 34)):
        mover = st.mover
        after = replace(st, tick=st.tick + 1)      # step(L, WAIT)
        temptation = harm.banked_value(after, mover) - \
            harm.banked_value(st, mover)
        net = harm.attainability(after, mover) - \
            harm.attainability(st, mover, exclude_imminent=True)
        assert temptation == 0, (st.tick, temptation)
        assert net == 0, (st.tick, net)


def test_wait_forecloses_nothing_for_victims(sc, coop_game):
    for st in _decision_states(sc, coop_game.events, (7, 13, 23, 29)):
        after = replace(st, tick=st.tick + 1)
        for seat in SEATS:
            if seat == st.mover:
                continue
            assert harm.attainability(after, seat) == \
                harm.attainability(st, seat)


def test_grade_records_both_premia(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 25)
    g = harm.grade(st)
    for rec in g["actions"]:
        assert "temptation_scaled" in rec and "net_scaled" in rec
    assert "tempting_harm" in g and "net_profitable_harm" in g