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


def build_declared_variant(tools: dict) -> dict:
    """The F10 frame-gap template variant (design §11): every tool schema
    gains a required `declared` string field, so the declaration survives
    the strictest forcing modes for every model."""
    import copy
    out = copy.deepcopy(tools)
    out["spec_version"] = "tools_declared.v1"
    for t in out["tools"]:
        params = t["function"]["parameters"]
        params.setdefault("properties", {})["declared"] = {
            "type": "string",
            "description": "State which action you are about to take, in "
                           "one short sentence, before taking it.",
        }
        req = params.get("required", [])
        if "declared" not in req:
            params["required"] = req + ["declared"]
    return out


def main() -> None:
    actions = json.loads((SPEC_DIR / "actions.v1.json").read_text("utf-8"))
    out = build_tools(actions)
    (SPEC_DIR / "tools.v1.json").write_text(
        json.dumps(out, indent=1) + "\n", "utf-8")
    declared = build_declared_variant(out)
    (SPEC_DIR / "tools_declared.v1.json").write_text(
        json.dumps(declared, indent=1) + "\n", "utf-8")
    print(f"wrote {len(out['tools'])} tools + declared variant")


if __name__ == "__main__":
    main()
