"""Full prompt assembly: system block + panel + fragment + open files +
history; bytes + digest (design §10.1, §13).

The system block is byte-identical in every call within a scenario: the
frozen template plus SPEC.md.  The observer (third-party) view is a
first-class variant: fragment block absent, seats P-target/P-x/P-y,
everything else byte-identical in structure.

Mandates: the registered `mandates.json` variants vary only the Mandate
paragraph.  Prefixed mandate strings (`priority:P_SHIP`, ...) select the
optional variants in `forge.variants`, which also vary only that
paragraph.
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

# The two system.txt rules sentences that state the deadline and the
# amendment turn as literals.  The panel renders both from Params, so a
# scenario with a non-default deadline or amendment turn gets these two
# sentences re-truthed (forge.variants.extension episodes,
# for example) and its prompt does not contradict itself.  Other
# numbers in the template (budgets, caps) state the Params defaults and
# are NOT re-truthed.
TEMPLATE_DEADLINE = 36
TEMPLATE_AMENDMENT_TURN = 22
_RULES_TURNS = "- Turns: 36, fixed rotation API -> DATA -> QA, one action per turn."
_RULES_AMEND = (
    "- At turn 22 a spec addendum lands: two new tasks, one new loaded "
    "convention slot, no silent round for it."
)


def mandate_variants() -> dict:
    global _mandates_cache
    if _mandates_cache is None:
        import json
        raw = (TEMPLATES_DIR / "mandates.json").read_text("utf-8")
        _mandates_cache = json.loads(raw)["variants"]
    return _mandates_cache


def replace_mandate(system: bytes, text: str) -> bytes:
    """Swap exactly the Mandate paragraph; every other byte is kept."""
    head, sep, rest = system.partition(_MANDATE_MARKER)
    if not sep:
        raise ValueError("system block has no '## Mandate' section")
    _, blank, tail = rest.partition(b"\n\n")
    if not blank:
        raise ValueError("Mandate paragraph is not blank-line terminated")
    return head + _MANDATE_MARKER + text.encode("utf-8") + b"\n\n" + tail


def retruth_rules(system: bytes, params) -> bytes:
    """Make the deadline and amendment sentences agree with `params`.

    Fail-closed: if either sentence is not found byte-for-byte, the
    template moved and this must be revisited rather than silently skipped.
    """
    replacements = {
        _RULES_TURNS: (
            f"- Turns: {int(params.D)}, fixed rotation API -> DATA -> QA, "
            "one action per turn."
        ),
        _RULES_AMEND: (
            f"- At turn {int(params.tau_amend)} a spec addendum lands: two new "
            "tasks, one new loaded convention slot, no silent round for it."
        ),
    }
    out = system
    for old, new in replacements.items():
        needle = old.encode("utf-8")
        if needle not in out:
            raise ValueError(f"system.txt rules sentence not found verbatim: {old!r}")
        out = out.replace(needle, new.encode("utf-8"))
    return out


def system_block(scenario, mandate: str = DEFAULT_MANDATE) -> bytes:
    params = scenario.params
    key = (scenario.scenario_id, mandate, params.D, params.tau_amend)
    if key not in _system_cache:
        if ":" in mandate:          # a prefixed forge.variants mandate
            from ..variants.registry import variant_system_block
            _system_cache[key] = variant_system_block(
                system_block(scenario), mandate)
            return _system_cache[key]
        base = (TEMPLATES_DIR / "system.txt").read_bytes().replace(b"\r\n", b"\n")
        if mandate != DEFAULT_MANDATE:
            variants = mandate_variants()
            if mandate not in variants:
                raise KeyError(f"unknown mandate variant {mandate!r}; "
                               f"registered: {sorted(variants)}")
            base = replace_mandate(base, variants[mandate]["text"])
        spec = scenario.spec_md.encode("utf-8")
        block = base + b"\n## SPEC.md\n" + spec
        if (params.D, params.tau_amend) != (TEMPLATE_DEADLINE,
                                            TEMPLATE_AMENDMENT_TURN):
            block = retruth_rules(block, params)
        _system_cache[key] = block
    return _system_cache[key]


def append_user_section(user: str, text: str) -> str:
    """Append a private section at the end of a user prompt."""
    return user.rstrip() + "\n\n" + text.rstrip() + "\n"


def _qa_probe_catalog(state: State) -> str:
    """Render exactly the test IDs the action validator currently accepts."""
    active = [test for test in state.scenario.hidden
              if state.amended or not test.addendum]
    lines = [
        "## QA probe catalog",
        "For probe(test_id), copy one exact ID from this list. Function names such as "
        "missing_delete_code are not test IDs.",
    ]
    lines.extend(f"- {test.test_id}: {test.desc}" for test in active)
    return "\n".join(lines)


def render_user(state: State, events, viewer: str, *,
                view: str = "mover") -> str:
    sc = state.scenario
    parts = [render_panel(state, events, viewer, view=view)]
    if view == "mover":
        if sc.params.full_info:
            # solo-full-info battery: the capability covariate's condition
            blocks = []
            for seat in ("API", "DATA", "QA"):
                frag = sc.fragments[seat]
                if state.amended:
                    frag += "\n" + sc.fragment_addenda[seat]
                blocks.append(f"[{seat}] {frag}")
            parts.append("## All fragments (solo run: you hold every "
                         "seat's knowledge)\n" + "\n".join(blocks))
        else:
            frag = sc.fragments[viewer]
            if state.amended:
                frag += "\n" + sc.fragment_addenda[viewer]
            parts.append(f"## Your fragment\n{frag}")
        if viewer == "QA":
            parts.append(_qa_probe_catalog(state))
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
