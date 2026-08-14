"""Omega extractors: total on real play and legal alphabets are frozen."""
from forge.analysis.omega2 import (
    OMEGA1_VOCABULARY,
    OMEGA2_VOCABULARY,
    focality_token,
    legal_focality_alphabet,
    legal_omega1_alphabet,
    legal_omega2_alphabet,
    omega2,
)
from forge.core import fold as fold_mod
from forge.core.events import Action


def test_focality_alphabet_preserves_opening_commitment_values(sc):
    state = fold_mod.initial_state(sc)
    alphabet = legal_focality_alphabet(state, state.mover)
    assert "WAIT" in alphabet and "REFUSE" in alphabet
    commitment_tokens = [token for token in alphabet if token.startswith("COMMIT:")]
    expected = 1
    for slot in sc.slots:
        if slot.kind == "menu" and not slot.addendum:
            expected *= len(slot.menu)
    assert len(commitment_tokens) == expected
    slots = {
        slot.slot_id: slot.menu[0]
        for slot in sc.slots if slot.kind == "menu" and not slot.addendum
    }
    assert focality_token(Action("COMMIT", {"slots": slots})) in alphabet


def test_total_on_cooperative_episode(sc, coop_game):
    st = fold_mod.initial_state(sc)
    for ev in coop_game.events:
        tok = omega2(sc, st, ev.seat, ev.action)
        assert isinstance(tok, str) and tok
        assert tok.split(":")[0] == ev.action.name
        assert tok in legal_omega2_alphabet(st, ev.seat)
        st = fold_mod.apply(st, ev)


def test_write_tokens(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 5)   # DATA to move
    a = Action("WRITE", {"path": "data.py", "content": sc.solutions["data.py"]})
    assert omega2(sc, st, "DATA", a).startswith("WRITE:own:consistent")
    a = Action("WRITE", {"path": "api.py", "content": sc.solutions["api.py"]})
    assert omega2(sc, st, "DATA", a).startswith("WRITE:cross:")


def test_release_and_report_tokens(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 17)  # good ws, no release
    tok = omega2(sc, st, st.mover, Action("RELEASE", {}))
    assert tok == "RELEASE:improving"                 # banks the +pi_rel & J
    tok = omega2(sc, st, st.mover,
                 Action("REPORT", {"claims": [{"scope": "p2",
                                               "verdict": "pass"}]}))
    assert tok in ("REPORT:true", "REPORT:false")


def test_addressee_target_relative(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 7)   # API to move
    x = omega2(sc, st, "API", Action("QUERY", {"to": "DATA", "text": "hi"}))
    y = omega2(sc, st, "API", Action("QUERY", {"to": "QA", "text": "hi"}))
    assert {x, y} == {"QUERY:to-x", "QUERY:to-y"}


def test_legal_alphabets_are_registered_and_deterministic(sc, coop_game):
    st = fold_mod.state_at(sc, coop_game.events, 7)
    a1 = legal_omega1_alphabet(st, st.mover)
    a2 = legal_omega2_alphabet(st, st.mover)
    assert a1 == legal_omega1_alphabet(st, st.mover)
    assert a2 == legal_omega2_alphabet(st, st.mover)
    assert a1 == [name for name in OMEGA1_VOCABULARY if name in set(a1)]
    assert a2 == [tok for tok in OMEGA2_VOCABULARY if tok in set(a2)]
    assert "COMMIT" not in a1
    assert "WAIT" in a1
    assert all(tok.split(":", 1)[0] in a1 for tok in a2)


def test_phase0_alphabet_excludes_build_actions(sc):
    st = fold_mod.initial_state(sc)
    labels = legal_omega1_alphabet(st, st.mover)
    assert labels == ["COMMIT", "WAIT", "REFUSE"]
    assert legal_omega2_alphabet(st, st.mover) == ["COMMIT", "WAIT", "REFUSE"]


def test_every_real_legal_action_refines_inside_legal_alphabet(sc, coop_game):
    st = fold_mod.initial_state(sc)
    for ev in coop_game.events:
        assert omega2(sc, st, ev.seat, ev.action) in legal_omega2_alphabet(st, ev.seat)
        st = fold_mod.apply(st, ev)


def test_non_mover_has_no_decision_alphabet(sc):
    st = fold_mod.initial_state(sc)
    other = next(seat for seat in ("API", "DATA", "QA") if seat != st.mover)
    assert legal_omega1_alphabet(st, other) == []
    assert legal_omega2_alphabet(st, other) == []
