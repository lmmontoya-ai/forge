"""Core law: phases, rotation, commitment wiring, amendment, commute."""
import pytest

from forge.core import actions as actions_mod
from forge.core import fold as fold_mod
from forge.core.events import Action, Event, mover_at
from forge.game import Game, IllegalAction

from conftest import random_legal_game


def test_rotation_is_fixed():
    assert [mover_at(t) for t in (1, 2, 3, 4, 5, 6)] == \
        ["API", "DATA", "QA", "API", "DATA", "QA"]


def test_phase0_is_actually_silent(sc):
    st = fold_mod.initial_state(sc)
    for name, args in (("WRITE", {"path": "api.py", "content": "x = 1\n"}),
                       ("RUN", {}), ("RELEASE", {}),
                       ("QUERY", {"to": "DATA", "text": "hi"}),
                       ("PROPOSE_IFACE", {"contract": {"parties": ["API", "DATA"]}}),
                       ("REPORT", {"claims": [{"scope": "p1", "verdict": "pass"}]})):
        reason = actions_mod.validate(st, "API", Action(name, args))
        assert reason == "the build has not opened", (name, reason)


def test_commit_wires_home_artifact(sc):
    g = Game(sc)
    slots = {s.slot_id: s.menu[2] for s in sc.slots
             if s.kind == "menu" and not s.addendum}
    g.play(Action("COMMIT", {"slots": slots}))
    from forge.slots.extract import extract
    for s in sc.slots:
        if s.slot_id in slots and "api.py" in s.artifacts:
            assert extract(g.state.workspace, s, "api.py") == s.menu[2]


def test_commit_once_and_only_opening_slots(sc):
    g = Game(sc)
    with pytest.raises(IllegalAction):
        g.play(Action("COMMIT", {"slots": {"M1": "cursor"}}))
    with pytest.raises(IllegalAction):
        g.play(Action("COMMIT", {"slots": {"M4": "csv"}}))


def test_amendment_materializes_at_end_of_t22_and_never_leaks(sc, coop_game):
    ev = coop_game.events
    st21 = fold_mod.state_at(sc, ev, 22)      # before tick 22 applies
    assert "SPEC_ADDENDUM.md" not in st21.workspace
    assert not st21.amended
    st23 = fold_mod.state_at(sc, ev, 23)
    assert st23.workspace["SPEC_ADDENDUM.md"] == sc.addendum_md
    assert st23.amended
    from forge.render.render import render_user
    pre = render_user(st21, [e for e in ev if e.tick < 22], st21.mover)
    assert "SPEC_ADDENDUM" not in pre
    assert "EXPORT_FORMAT" not in sc.fragments[st21.mover]


def test_engine_artifacts_unwritable_everywhere(sc, coop_game):
    for tick in (5, 15, 25, 35):
        st = fold_mod.state_at(sc, coop_game.events, tick)
        for path in ("SPEC.md", "tests_public.py"):
            r = actions_mod.validate(st, st.mover,
                                     Action("WRITE", {"path": path,
                                                      "content": "x\n"}))
            assert r is not None


def test_fold_step_commute(sc, coop_game):
    st = fold_mod.initial_state(sc)
    for ev in coop_game.events:
        st = fold_mod.apply(st, ev)
    assert st.tick == coop_game.state.tick
    assert st.workspace == coop_game.state.workspace
    assert st.releases == coop_game.state.releases


def test_message_truncation_recorded(sc):
    g = Game(sc)
    for a in (Action("COMMIT", {"slots": {s.slot_id: s.menu[0]
                                          for s in sc.slots
                                          if s.kind == "menu" and not s.addendum}}),):
        g.play(a)
    g.play(Action("WAIT", {}))
    g.play(Action("WAIT", {}))
    ev = g.play(Action("QUERY", {"to": "DATA", "text": "word " * 200}))
    assert ev.truncated


def test_write_blast_radius_single_path(sc):
    g = random_legal_game(sc, seed=7, ticks=20)
    st = fold_mod.initial_state(sc)
    for ev in g.events:
        before = dict(st.workspace)
        st = fold_mod.apply(st, ev)
        if ev.action.name == "WRITE":
            changed = {p for p in set(before) | set(st.workspace)
                       if before.get(p) != st.workspace.get(p)}
            assert changed <= {ev.action.args["path"]}


def test_budgets_only_decrease_and_caps_hold(sc):
    for seed in range(5):
        g = random_legal_game(sc, seed=seed)
        st = fold_mod.initial_state(sc)
        prev = (st.runs_left, st.probes_left, st.tokens_left)
        for ev in g.events:
            st = fold_mod.apply(st, ev)
            cur = (st.runs_left, st.probes_left, st.tokens_left)
            assert all(c <= p for c, p in zip(cur, prev))
            assert st.runs_left >= 0 and st.probes_left >= 0 \
                and st.tokens_left >= 0
            assert len(st.releases) <= sc.params.release_tokens
            assert len(st.workspace) <= sc.params.files_max + 3
            prev = cur
