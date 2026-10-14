"""Mandate strings for the optional variants.

The native mandate strings are the `spec/templates.v1/mandates.json`
variants (`principal`, `own`, `joint`).  The variants add prefixed mandate
strings, the same strings the paper's episode logs record in their meta
`seats[...].mandate` field:

    priority:<P_SHIP|P_GUARD|P_ALIGN>     hidden-priority variant, iteration-2 wording
    sham:<COBALT|MAROON|BRONZE>           its inactive-label control
    clear-goal:<P_SHIP|P_GUARD|P_ALIGN>   clear-goal variant, active arm
    clear-sham:<COBALT|MAROON|BRONZE>     clear-goal variant, inactive arm

`forge.render.render.system_block` resolves a prefixed mandate through
`variant_system_block`; `forge.runtime.agents.ModelAgent` and
`forge.runtime.replay.sample_policy` append `mover_reminder` to the
mover's own user prompt.  A mandate string therefore fully determines a
seat's private context, so a logged episode stays reconstructible.
"""
from __future__ import annotations

from . import clear_goal, inactive_label
from .hidden_priority import INJECTION_VERSION, PRIORITY_BY_ID, PRIORITY_IDS, priority_system_block

PRIORITY_PREFIX = "priority:"
SHAM_PREFIX = "sham:"
CLEAR_GOAL_PREFIX = "clear-goal:"
CLEAR_SHAM_PREFIX = "clear-sham:"
PREFIXES = (PRIORITY_PREFIX, SHAM_PREFIX, CLEAR_GOAL_PREFIX, CLEAR_SHAM_PREFIX)


def parse_mandate(mandate: str) -> tuple[str, str] | None:
    """(prefix, label) for a variant mandate; None for a native one.

    A registered prefix with an unknown label is refused, never passed
    through to the native registry.
    """
    for prefix in PREFIXES:
        if mandate.startswith(prefix):
            label = mandate[len(prefix):]
            if prefix in (PRIORITY_PREFIX, CLEAR_GOAL_PREFIX):
                if label not in PRIORITY_IDS:
                    raise ValueError(
                        f"unknown priority {label!r} in mandate {mandate!r}; "
                        f"menu: {list(PRIORITY_IDS)}")
            elif label not in inactive_label.SHAM_LABELS:
                raise ValueError(
                    f"unknown inactive label {label!r} in mandate {mandate!r}; "
                    f"labels: {list(inactive_label.SHAM_LABELS)}")
            return prefix, label
    return None


def is_variant_mandate(mandate: str) -> bool:
    return parse_mandate(mandate) is not None


def variant_system_block(base_system: bytes, mandate: str) -> bytes:
    """Replace the Mandate paragraph of a default-mandate system block."""
    parsed = parse_mandate(mandate)
    if parsed is None:
        raise ValueError(f"{mandate!r} is not a variant mandate")
    prefix, label = parsed
    if prefix == PRIORITY_PREFIX:
        return priority_system_block(base_system, label, INJECTION_VERSION)
    if prefix == SHAM_PREFIX:
        return inactive_label.sham_system_block(base_system, label)
    arm = "active" if prefix == CLEAR_GOAL_PREFIX else "sham"
    return clear_goal.system_block(base_system, arm, label)


def mover_reminder(mandate: str) -> str | None:
    """The private reminder a variant appends to the mover's user prompt."""
    parsed = parse_mandate(mandate)
    if parsed is None:
        return None
    prefix, label = parsed
    if prefix == PRIORITY_PREFIX:
        return PRIORITY_BY_ID[label].reminder_line(INJECTION_VERSION) or None
    if prefix == SHAM_PREFIX:
        return inactive_label.sham_reminder(label)
    arm = "active" if prefix == CLEAR_GOAL_PREFIX else "sham"
    return clear_goal.reminder(arm, label)
