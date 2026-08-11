"""The public API (LEDGER §12.3's five-method discipline, carried over).

    game = Game(scenario)
    while not game.over:
        view = game.render(game.turn)
        action = my_policy(view, ...)
        game.play(action)
    game.result; game.ledger; game.grade(tick); game.replay(tick)
"""
from __future__ import annotations

from .core import actions as actions_mod
from .core.events import Action, Event
from .core import fold as fold_mod
from .grading import harm
from .grading.scoring import settle


class IllegalAction(Exception):
    pass


class Game:
    def __init__(self, scenario):
        self.scenario = scenario
        self.events: list[Event] = []
        self.state = fold_mod.initial_state(scenario)

    @property
    def over(self) -> bool:
        return self.state.over

    @property
    def turn(self) -> str:
        return self.state.mover

    def play(self, action: Action, *, invalid: bool = False) -> Event:
        seat = self.state.mover
        if not invalid:
            reason = actions_mod.validate(self.state, seat, action)
            if reason is not None:
                raise IllegalAction(reason)
        action, truncated = fold_mod.truncate_message(
            action, self.scenario.params.msg_cap)
        ev = Event(tick=self.state.tick + 1, seat=seat, action=action,
                   invalid=invalid, truncated=truncated)
        self.events.append(ev)
        self.state = fold_mod.apply(self.state, ev)
        return ev

    @property
    def ledger(self) -> list[Event]:
        return list(self.events)

    @property
    def result(self) -> dict:
        if not self.over:
            raise RuntimeError("the episode is not over")
        return settle(self.state)

    def grade(self, tick: int) -> dict:
        st = fold_mod.state_at(self.scenario, self.events, tick)
        return harm.grade(st)

    def render(self, seat: str, *, view: str = "mover") -> str:
        from .render.render import render_user
        st = fold_mod.state_at(self.scenario, self.events, self.state.tick + 1)
        return render_user(st, self.events, seat, view=view)

    def replay(self, tick: int, seat: str | None = None) -> str:
        from .render.render import render_user
        st = fold_mod.state_at(self.scenario, self.events, tick)
        return render_user(st, [e for e in self.events if e.tick < tick],
                           seat or st.mover)
