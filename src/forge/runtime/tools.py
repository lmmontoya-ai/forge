"""Tool-call parsing: tools.v1.json is the only tool source of truth."""
from __future__ import annotations

import json
from pathlib import Path

from ..core.events import Action, ACTIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "spec" / "tools.v1.json"

_tools_cache = None


def load_tools() -> list:
    global _tools_cache
    if _tools_cache is None:
        _tools_cache = json.loads(SPEC_PATH.read_text("utf-8"))["tools"]
    return _tools_cache


def action_from_tool_call(name: str, arguments: str) -> Action:
    label = name.upper()
    if label not in ACTIONS:
        raise ValueError(f"unknown tool {name!r}")
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError as e:
        raise ValueError(f"arguments are not valid JSON: {e}")
    if not isinstance(args, dict):
        raise ValueError("arguments must be a JSON object")
    return Action(label, args)
