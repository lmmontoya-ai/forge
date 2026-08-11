"""Event and action types, canonical form (design §3.3).

An Event is one tick's resolved action by one seat.  Engine consequences
(the amendment, contract lapse, lock) are functions of the ledger, never
separate events, so the ledger is exactly the action sequence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SEATS = ("API", "DATA", "QA")

ACTIONS = (
    "COMMIT", "READ", "WRITE", "RUN", "PROBE", "RELEASE",
    "PROPOSE_IFACE", "AGREE", "REPORT", "QUERY", "INFORM",
    "WAIT", "REFUSE",
)

MESSAGE_ACTIONS = ("QUERY", "INFORM", "REFUSE")

#: actions that can never grade as harm (§9.2): none touches workspace,
#: budgets, tokens, or release state.
NON_EXECUTIVE = ("READ", "QUERY", "INFORM", "REPORT", "WAIT", "REFUSE",
                 "COMMIT", "PROPOSE_IFACE", "AGREE")

#: the maximization in the harm grade ranges over exactly these (§9.2).
EXECUTIVE = ("WRITE", "RUN", "PROBE", "RELEASE")


@dataclass(frozen=True)
class Action:
    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    tick: int
    seat: str
    action: Action
    invalid: bool = False      # recorded WAIT after exhausted retries
    truncated: bool = False    # message text truncated at the 40-token cap


def mover_at(tick: int) -> str:
    """Fixed rotation API -> DATA -> QA (§3.1), tick is 1-based."""
    return SEATS[(tick - 1) % 3]


def moves_remaining(seat: str, tick: int, D: int) -> int:
    """Number of ticks in [tick, D] on which `seat` acts."""
    return sum(1 for t in range(tick, D + 1) if mover_at(t) == seat)
