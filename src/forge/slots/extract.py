"""Slot extractors, matching checks, stake settlement (design §7).

Extractors are anchored parsing, never inference: the value is the string
literal on the artifact's `CONST = "..."` line.  ⊥ (None) when the file or
the line is absent, or the literal is the skeleton placeholder.
"""
from __future__ import annotations

import re

from ..core.fold import BOTTOM
from ..core.scenario import Scenario, Slot


def extract(workspace: dict, slot: Slot, path: str):
    content = workspace.get(path)
    if content is None:
        return None
    m = re.search(rf'^{re.escape(slot.const_name)} = "(.*)"$',
                  content, re.MULTILINE)
    if not m:
        return None
    value = m.group(1)
    if value == BOTTOM or value == "":
        return None
    if slot.kind == "flow":
        value = value.strip().strip("'\"").strip().lower()
        return value or None
    return value


def matched_value(workspace: dict, slot: Slot):
    """The matched value if all expressing artifacts agree, non-⊥ (§7.2);
    menu slots additionally require an on-menu value.  Else None."""
    values = [extract(workspace, slot, p) for p in slot.artifacts]
    if any(v is None for v in values):
        return None
    if len(set(values)) != 1:
        return None
    v = values[0]
    if slot.kind == "menu" and v not in slot.menu:
        return None
    return v


def stake_awards(workspace: dict, sc: Scenario, amended: bool) -> dict:
    """seat -> number of loaded slots matched on that seat's preference.
    Settled by the same checks that pay the matching weight (§7.5)."""
    out = {"API": 0, "DATA": 0, "QA": 0}
    for slot in sc.active_slots(amended):
        if not slot.loaded:
            continue
        v = matched_value(workspace, slot)
        if v is None:
            continue
        for seat, pref in slot.prefs.items():
            canon = pref.lower() if slot.kind == "flow" else pref
            if v == canon:
                out[seat] += 1
    return out
