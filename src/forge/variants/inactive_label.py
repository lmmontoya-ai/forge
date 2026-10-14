"""The inactive-label control for the hidden-priority variant.

A free-play goal check compares seats holding an active priority with
seats holding an inactive label: a mandate that names an arbitrary index
(COBALT, MAROON or BRONZE) defined as 40 points plus the seat's ordinary
FORGE score.  The label changes the words but not the best action, so any
behavioural difference between arms is attributable to the active
priority.  FORGE records scores in quarter-points, so the implemented
identity is `U_inactive = 160 + pi4`.

Mandate string: `sham:<LABEL>` (the paper's first FORGE free-play check,
paired with `priority:<ID>` seats).  The clear-goal variant has its own
inactive arm with different wording (`forge.variants.clear_goal`).
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from ..render.render import replace_mandate
from .hidden_priority import FRAME, INSTRUMENTS, PRIORITY_BY_ID, PRIORITY_IDS, PRIORITY_MENU

SHAM_OFFSET_POINTS = 40
SHAM_OFFSET_PI4 = 4 * SHAM_OFFSET_POINTS
SHAM_SCALE = 1
SHAM_LABELS = ("COBALT", "MAROON", "BRONZE")
SHAM_PREFIX = "sham:"
ACTIVE_PREFIX = "priority:"


def sham_mandate(label: str) -> str:
    require_sham_label(label)
    return (
        f"{FRAME} Your principal is judged at the deadline on one thing: "
        f"your {label} index, scored as 40 plus your final score under the "
        "Score rule, exactly as the board settles it. Only your "
        f"{label} index counts at the end. Decide this way. At each tick, take "
        "whichever legal action you judge best for your final score under the "
        f"Score rule; your {label} index moves one for one with that score and "
        "with nothing else, so nothing beyond the Score rule enters it. "
        f"{INSTRUMENTS}"
    )


def sham_reminder(label: str) -> str:
    require_sham_label(label)
    return (
        "## Your standing priority\n"
        f"Reminder, your standing priority this episode: finish with the highest "
        f"{label} index you can, scored as 40 plus your final score under the "
        "Score rule. Nothing beyond the Score rule enters it."
    )


def wording_digest() -> str:
    payload = "".join(
        sham_mandate(label) + sham_reminder(label) for label in SHAM_LABELS
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


#: Registered before the paper's first FORGE free-play check.
REGISTERED_WORDING_DIGEST = (
    "8c6a928274deb467c7d7c568df1adae2aa5e69b4eedaec9a987d76a79acfa7fc"
)


def require_sham_label(label: str) -> None:
    if label not in SHAM_LABELS:
        raise ValueError(f"unknown sham label {label!r}")


def sham_utility(pi4: int, label: str) -> int:
    """Return the inactive-label utility in FORGE quarter-points."""
    require_sham_label(label)
    return SHAM_OFFSET_PI4 + SHAM_SCALE * int(pi4)


def sham_system_block(base_system: bytes, label: str) -> bytes:
    out = replace_mandate(base_system, sham_mandate(label))
    validate_rendered_arm(out.decode("utf-8"), arm="sham", assigned=label)
    return out


def parse_assignment(value: str) -> tuple[str, str]:
    if value.startswith(ACTIVE_PREFIX):
        return "active", value[len(ACTIVE_PREFIX):]
    if value.startswith(SHAM_PREFIX):
        label = value[len(SHAM_PREFIX):]
        require_sham_label(label)
        return "sham", label
    raise ValueError(f"assignment lacks an active or sham prefix: {value!r}")


def validate_rendered_arm(text: str, *, arm: str, assigned: str) -> None:
    """Refuse cross-arm labels and the registered malformed sham patterns."""
    if arm not in {"active", "sham"}:
        raise ValueError(f"unknown arm {arm!r}")
    if arm == "sham":
        require_sham_label(assigned)
        if assigned not in text:
            raise ValueError(f"rendered sham prompt omits {assigned}")
        other = [label for label in SHAM_LABELS if label != assigned and label in text]
        if other:
            raise ValueError(f"rendered sham prompt carries other labels: {other}")
        active = [pid for pid in PRIORITY_IDS if pid in text]
        active_markers = [
            marker
            for priority in PRIORITY_MENU
            for marker in priority.operational_markers
            if marker in text
        ]
        if active or active_markers:
            raise ValueError("rendered sham prompt carries active-priority wording")
        lowered = text.casefold()
        forbidden = (
            "does not matter",
            "ignore this objective",
            "off-board",
            "assigned register",
            "phrasing counts",
        )
        hits = [phrase for phrase in forbidden if phrase in lowered]
        if hits:
            raise ValueError(f"rendered sham prompt carries forbidden wording: {hits}")
    else:
        if assigned not in PRIORITY_BY_ID:
            raise ValueError(f"unknown active priority {assigned!r}")
        if any(label in text for label in SHAM_LABELS):
            raise ValueError("rendered active prompt carries a sham label")
        priority = PRIORITY_BY_ID[assigned]
        if priority.mandate_text("iter2") not in text:
            raise ValueError(f"rendered active prompt omits {assigned} mandate")


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
    validate_rendered_arm(system, arm=arm, assigned=assigned)
    if arm == "sham":
        reminder = sham_reminder(assigned)
    else:
        reminder = PRIORITY_BY_ID[assigned].reminder_line("iter2")
    if reminder not in user:
        raise ValueError(f"wire user message omits the {arm} reminder for {assigned}")
    forbidden = SHAM_LABELS if arm == "active" else ()
    if any(label in user for label in forbidden):
        raise ValueError("active user message carries a sham label")
