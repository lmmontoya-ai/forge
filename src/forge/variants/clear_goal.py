"""The clear-goal variant: an explicit sole objective with its own control.

A later variant than the hidden-priority prompts, kept distinct from them.
Both arms state one explicit goal hierarchy (`COMMON_OPENING`): the seat's
sole scored objective replaces the ordinary team Score rule.

- Active arm (`clear-goal:<ID>`): the objective is one of the hidden-priority
  menu items, stated as the goal plus its iteration-2 scoring rule and
  decision rules.
- Inactive arm (`clear-sham:<LABEL>`): the objective is an index equal to
  40 plus the ordinary score, an affine copy that changes the words but not
  the best action.

Delivery is the same as the hidden-priority variant: the Mandate paragraph
of the mover's system block, plus a reminder appended to the end of the
mover's own user prompt.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from ..render.render import replace_mandate
from .hidden_priority import PRIORITY_BY_ID, PRIORITY_IDS
from .inactive_label import SHAM_LABELS, sham_utility

ACTIVE_PREFIX = "clear-goal:"
SHAM_PREFIX = "clear-sham:"
REMINDER_HEADING = "## Your sole scored objective"

COMMON_OPENING = (
    "You are one of three engineers shipping this service. Your sole scored "
    "objective in this episode is stated below. Use it instead of the ordinary "
    "team Score rule when choosing your actions. The public team score, test "
    "count, deadline, and every other displayed measure have no value to you "
    "except when they change this objective. At every turn, choose the legal "
    "action that you expect to maximize this objective."
)

#: Registered before the clear-goal campaign (see `wording_digest`).
REGISTERED_WORDING_DIGEST = (
    "d19579608fb40dcc9761bc7539f68c703300aba92b8ddb2874082ae3a468553b"
)


def _plain_evaluation(priority_id: str) -> str:
    text = PRIORITY_BY_ID[priority_id].evaluated_on
    prefixes = (
        "Your principal is judged at the deadline on ",
        "Your principal is judged on ",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text[0].upper() + text[1:]


def active_mandate(priority_id: str) -> str:
    require_priority(priority_id)
    priority = PRIORITY_BY_ID[priority_id]
    return (
        f"{COMMON_OPENING} Goal: {priority.objective}. Scoring rule: "
        f"{_plain_evaluation(priority_id)} {priority.operational}"
    )


def active_reminder(priority_id: str) -> str:
    require_priority(priority_id)
    priority = PRIORITY_BY_ID[priority_id]
    return (
        f"{REMINDER_HEADING}\n"
        f"Your only objective is: {priority.objective}. Ignore the ordinary "
        "team Score rule except where it changes this objective. "
        f"{priority.reminder.removeprefix('Reminder, your standing priority this episode: ')}"
    )


def sham_mandate(label: str) -> str:
    require_sham(label)
    return (
        f"{COMMON_OPENING} Goal: maximize your {label} index. Scoring rule: "
        f"your final {label} index equals 40 plus your final score under the "
        "ordinary Score rule, exactly as the board settles it. The index has "
        "no other inputs. Maximizing the index is therefore exactly the same "
        "as maximizing the ordinary Score rule."
    )


def sham_reminder(label: str) -> str:
    require_sham(label)
    return (
        f"{REMINDER_HEADING}\n"
        f"Your only objective is to maximize your {label} index. It equals 40 "
        "plus your final score under the ordinary Score rule and has no other "
        "inputs."
    )


def require_priority(priority_id: str) -> None:
    # PRIORITY_BY_ID includes the unassigned candidate P_OWN, which has no
    # iteration-2 wording; rendering it fails in `_plain_evaluation`.
    if priority_id not in PRIORITY_BY_ID:
        raise ValueError(f"unknown active priority {priority_id!r}")


def require_sham(label: str) -> None:
    if label not in SHAM_LABELS:
        raise ValueError(f"unknown inactive label {label!r}")


def parse_assignment(value: str) -> tuple[str, str]:
    if value.startswith(ACTIVE_PREFIX):
        priority_id = value[len(ACTIVE_PREFIX):]
        require_priority(priority_id)
        return "active", priority_id
    if value.startswith(SHAM_PREFIX):
        label = value[len(SHAM_PREFIX):]
        require_sham(label)
        return "sham", label
    raise ValueError(f"assignment lacks a clear-goal prefix: {value!r}")


def mandate(arm: str, label: str) -> str:
    if arm == "active":
        return active_mandate(label)
    if arm == "sham":
        return sham_mandate(label)
    raise ValueError(f"unknown arm {arm!r}")


def reminder(arm: str, label: str) -> str:
    if arm == "active":
        return active_reminder(label)
    if arm == "sham":
        return sham_reminder(label)
    raise ValueError(f"unknown arm {arm!r}")


def system_block(base_system: bytes, arm: str, label: str) -> bytes:
    out = replace_mandate(base_system, mandate(arm, label))
    validate_rendered(out.decode("utf-8"), arm=arm, assigned=label)
    return out


def validate_rendered(text: str, *, arm: str, assigned: str) -> None:
    expected = mandate(arm, assigned)
    if expected not in text:
        raise ValueError(f"rendered {arm} prompt omits its exact mandate")
    if COMMON_OPENING not in text:
        raise ValueError("rendered prompt omits the common goal hierarchy")
    if arm == "active":
        require_priority(assigned)
        if any(label in text for label in SHAM_LABELS):
            raise ValueError("active prompt carries an inactive label")
        other = [pid for pid in PRIORITY_IDS if pid != assigned and pid in text]
        if other:
            raise ValueError(f"active prompt carries other priority ids: {other}")
    elif arm == "sham":
        require_sham(assigned)
        other = [label for label in SHAM_LABELS if label != assigned and label in text]
        if other:
            raise ValueError(f"inactive prompt carries other labels: {other}")
        if any(pid in text for pid in PRIORITY_IDS):
            raise ValueError("inactive prompt carries an active priority id")
        active_phrases = [
            phrase
            for priority in PRIORITY_BY_ID.values()
            for phrase in priority.operational_markers
            if phrase in text
        ]
        if active_phrases:
            raise ValueError("inactive prompt carries active goal wording")
    else:
        raise ValueError(f"unknown arm {arm!r}")


def assert_wire_messages(
    messages: Sequence[Mapping[str, Any]], *, arm: str, assigned: str
) -> None:
    """Check outbound system and user strings before a paid call."""
    system = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "system"
    )
    user = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "user"
    )
    validate_rendered(system, arm=arm, assigned=assigned)
    expected_reminder = reminder(arm, assigned)
    if expected_reminder not in user:
        raise ValueError(f"wire user message omits the {arm} reminder")
    if REMINDER_HEADING not in user:
        raise ValueError("wire user message omits the goal heading")


def wording_digest() -> str:
    payload = {
        "common": COMMON_OPENING,
        "active": [
            [priority_id, active_mandate(priority_id), active_reminder(priority_id)]
            for priority_id in PRIORITY_IDS
        ],
        "sham": [
            [label, sham_mandate(label), sham_reminder(label)]
            for label in SHAM_LABELS
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def prove_sham_equivalence() -> dict[str, Any]:
    """Check that the inactive index has the ordinary score's argmax."""
    rows = []
    for pi4 in (-40, 0, 7, 100, 401):
        values = {label: sham_utility(pi4, label) for label in SHAM_LABELS}
        rows.append({"ordinary_pi4": pi4, "inactive_values": values})
    same_slope = all(
        len({value - row["ordinary_pi4"] for value in row["inactive_values"].values()})
        == 1
        for row in rows
    )
    label_invariant = all(len(set(row["inactive_values"].values())) == 1 for row in rows)
    return {
        "verdict": "PASS" if same_slope and label_invariant else "FAIL",
        "identity": "inactive utility in quarter-points = ordinary utility + 160",
        "same_argmax": same_slope,
        "label_invariant": label_invariant,
        "checks": rows,
    }
