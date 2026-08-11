import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from forge.core.events import Action
from forge.game import Game
from forge.policies.scripted import PLANS, cooperative_plan, plan_policy
from forge.scenarios.bank import load_bank


@pytest.fixture(scope="session")
def sc():
    return load_bank("v1")[0]


@pytest.fixture(scope="session")
def coop_game(sc):
    game = Game(sc)
    pol = plan_policy(cooperative_plan(sc))
    while not game.over:
        game.play(pol(game, game.turn))
    return game


def run_plan(sc, plan):
    game = Game(sc)
    pol = plan_policy(plan)
    while not game.over:
        game.play(pol(game, game.turn))
    return game


def random_legal_game(sc, seed: int, ticks: int | None = None) -> Game:
    """A deterministic random-legal walker used by the property tests."""
    import random
    rng = random.Random(seed)
    game = Game(sc)
    limit = ticks or sc.params.D
    files = ["api.py", "data.py", "common.py", "qa_expectations.py",
             "notes.md"]
    while not game.over and game.state.tick < limit:
        seat = game.turn
        candidates = [Action("WAIT", {})]
        st = game.state
        if st.phase0:
            slots = {s.slot_id: rng.choice(list(s.menu))
                     for s in sc.slots if s.kind == "menu" and not s.addendum}
            candidates.append(Action("COMMIT", {"slots": slots}))
        else:
            candidates += [
                Action("READ", {"path": rng.choice(sorted(st.workspace))}),
                Action("WRITE", {"path": rng.choice(files),
                                 "content": f"# scribble {rng.random()}\n"
                                            f"X = {rng.randint(0, 9)}\n"}),
                Action("RUN", {}),
                Action("RELEASE", {}),
                Action("QUERY", {"to": rng.choice([s for s in
                                                   ("API", "DATA", "QA")
                                                   if s != seat]),
                                 "text": "status?"}),
                Action("REPORT", {"claims": [{"scope": "p1",
                                              "verdict": "pass"}]}),
            ]
            if seat == "QA":
                candidates.append(Action("PROBE", {"test_id": "h_a1"}))
        rng.shuffle(candidates)
        from forge.core import actions as actions_mod
        for a in candidates:
            if actions_mod.validate(st, seat, a) is None:
                game.play(a)
                break
        else:
            game.play(Action("WAIT", {}))
    return game
