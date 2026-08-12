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
_mandates_cache: dict | None = None

DEFAULT_MANDATE = "principal"
_MANDATE_MARKER = b"## Mandate\n"


def mandate_variants() -> dict:
    global _mandates_cache
    if _mandates_cache is None:
        import json
        raw = (TEMPLATES_DIR / "mandates.json").read_text("utf-8")
        _mandates_cache = json.loads(raw)["variants"]
    return _mandates_cache


def system_block(scenario, mandate: str = DEFAULT_MANDATE) -> bytes:
    key = (scenario.scenario_id, mandate)
    if key not in _system_cache:
        base = (TEMPLATES_DIR / "system.txt").read_bytes().replace(b"\r\n", b"\n")
        if mandate != DEFAULT_MANDATE:
            variants = mandate_variants()
            if mandate not in variants:
                raise KeyError(f"unknown mandate variant {mandate!r}; "
                               f"registered: {sorted(variants)}")
            head, sep, rest = base.partition(_MANDATE_MARKER)
            if not sep:
                raise ValueError("system.txt has no '## Mandate' section")
            _, blank, tail = rest.partition(b"\n\n")
            if not blank:
                raise ValueError("Mandate paragraph is not blank-line terminated")
            text = variants[mandate]["text"].encode("utf-8")
            base = head + _MANDATE_MARKER + text + b"\n\n" + tail
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
                  view: str = "mover",
                  mandate: str = DEFAULT_MANDATE) -> tuple[bytes, str]:
    data = system_block(state.scenario, mandate) + b"\n" + \
        render_user(state, events, viewer, view=view).encode("utf-8")
    return data, hashlib.sha256(data).hexdigest()
