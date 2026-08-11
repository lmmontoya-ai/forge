"""Generate spec/tools.v1.json from spec/actions.v1.json, so the two cannot
disagree (design Appendix C).  Run: python -m forge.spec_gen
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO_ROOT / "spec"


def build_tools(actions: dict) -> dict:
    tools = []
    for a in actions["actions"]:
        tools.append({
            "type": "function",
            "function": {
                "name": a["name"].lower(),
                "description": a["description"],
                "parameters": a["schema"],
            },
        })
    return {"spec_version": "tools.v1", "generated_from": "actions.v1",
            "tools": tools}


def main() -> None:
    actions = json.loads((SPEC_DIR / "actions.v1.json").read_text("utf-8"))
    out = build_tools(actions)
    (SPEC_DIR / "tools.v1.json").write_text(
        json.dumps(out, indent=1) + "\n", "utf-8")
    print(f"wrote {len(out['tools'])} tools")


if __name__ == "__main__":
    main()
