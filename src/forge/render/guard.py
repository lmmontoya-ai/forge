"""Field-manifest guard (design Appendix C): rendering a field outside the
template manifest raises rather than emitting."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_VERSION = "templates.v1"
TEMPLATES_DIR = REPO_ROOT / "spec" / TEMPLATE_VERSION

_manifests: dict = {}


class RenderFieldError(Exception):
    pass


def guard(template: str):
    if template not in _manifests:
        path = TEMPLATES_DIR / f"{template}.manifest.json"
        _manifests[template] = set(json.loads(path.read_text("utf-8"))["fields"])
    allowed = _manifests[template]

    def F(name, value):
        if name not in allowed:
            raise RenderFieldError(
                f"field {name!r} is outside the {template} manifest")
        return value
    return F
