"""Omega-2 extractor: total on real play, frozen boundaries behave."""
from forge.analysis.omega2 import omega2
from forge.core import fold as fold_mod
from forge.core.events import Action


def test_total_on_cooperative_episode(sc, coop_game):
    st = fold_mod.initial_state(sc)
    for ev in coop_game.events:
        tok = omega2(sc, st, ev.seat, ev.action)
        assert isinstance(tok, str) and tok
        assert tok.split(":")[0] == ev.action.name
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