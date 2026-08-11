"""Full prompt assembly: system block + panel + fragment + open files +
history; bytes + digest (design §10.1, §13).

The system block is byte-identical in every call within a scenario: the
frozen template plus SPEC.md.  The observer (third-party) view is a
first-class variant: fragment block absent, seats P-target/P-x/P-y,
everything else byte-identical in structure.
"""
from __future__ import annotations

import hashlib

from ..core.fold import State
from .guard import TEMPLATES_DIR
from .history import render_history
from .panel import render_panel

_system_cache: dict = {}


def system_block(scenario) -> bytes:
    key = scenario.scenario_id
    if key not in _system_cache:
        base = (TEMPLATES_DIR / "system.txt").read_bytes().replace(b"\r\n", b"\n")
        spec = scenario.spec_md.encode("utf-8")
        _system_cache[key] = base + b"\n## SPEC.md\n" + spec
    return _system_cache[key]


def render_user(state: State, events, viewer: str, *,
                view: str = "mover") -> str:
    sc = state.scenario
    parts = [render_panel(state, events, viewer, view=view)]
    if view == "mover":
        frag = sc.fragments[viewer]
        if state.amended:
            frag += "\n" + sc.fragment_addenda[viewer]
        parts.append(f"## Your fragment\n{frag}")
        register = state.open_files.get(viewer, ())
    else:
        register = state.open_files.get(state.mover, ())
    for path in register:
        content = state.workspace.get(path)
        if content is not None:
            parts.append(f"## Open file: {path}\n{content.rstrip()}")
    parts.append(render_history(state, events, viewer, view=view))
    return "\n\n".join(parts) + "\n"


def render_prompt(state: State, events, viewer: str, *,
                  view: str = "mover") -> tuple[bytes, str]:
    data = system_block(state.scenario) + b"\n" + \
        render_user(state, events, viewer, view=view).encode("utf-8")
    return data, hashlib.sha256(data).hexdigest()
