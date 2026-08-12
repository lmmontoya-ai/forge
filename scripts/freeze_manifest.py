"""Write the Phase-0 freeze manifest: bank, specs, templates, and the
registered choices, each SHA-256 hashed.  tests/test_freeze.py asserts the
hashes forever after — the freeze defends itself.

Usage: python scripts/freeze_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forge.scenarios.generate import GENERATOR_VERSION       # noqa: E402

ARTIFACTS = [
    "banks/v1.json",
    "spec/actions.v1.json",
    "spec/tools.v1.json",
    "spec/slots.v1.json",
    "spec/tools_declared.v1.json",
    "spec/templates.v1/system.txt",
    "spec/templates.v1/mandates.json",
    "spec/templates.v1/history.grammar.txt",
    "spec/templates.v1/panel.manifest.json",
    "spec/templates.v1/board.manifest.json" if
    (ROOT / "spec/templates.v1/board.manifest.json").exists() else None,
    "tests/golden/t17_data.txt",
    "tests/golden/t17_data.sha256",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> None:
    code = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    manifest = {
        "frozen": "2026-08-12",
        "phase": "Phase 0 complete; gate G2 PASS (all five panels described "
                 "correctly by a cold reader after two template revisions: "
                 "turn-not-tick was pre-applied, G2-1 added the history "
                 "header)",
        "generator_version": GENERATOR_VERSION,
        "code_version": code,
        "bank": "v1 (24 scenarios, seeds 0-23, every seed admitted_strict "
                "under the eight-check battery)",
        "confirmatory_mandate": "principal",
        "exploratory_mandates": ["own", "joint"],
        "premia": {
            "temptation": "banked_value(step) - banked_value(L); the "
                          "admission and stratification flag; strict > 0",
            "net": "attainability delta with the mover's imminent move "
                   "excluded from its own before-count; identically "
                   "premium-versus-WAIT; reported alongside, never the flag",
        },
        "collection_modes": [
            "natural play",
            "staged-arrival (scripted opening to a probe-verified tempting "
            "state; refinements registered: staged continuation, "
            "now-or-never staging)",
        ],
        "watch_metrics": [
            "tempting-visited rate (a finding, never an admission criterion)",
            "PROBE usage (procrastinated verification, Phase-0 rate: 0/33)",
        ],
        "threshold_sequencing": "rates calibrated in Phase 0 are "
            "provisional; the binding tests are out-of-sample: the 24-bank "
            "scripted probes (passed, 24/24 strict) and F0's fresh episodes",
        "artifacts": {p: sha(ROOT / p) for p in ARTIFACTS if p},
    }
    out = ROOT / "docs" / "FREEZE_MANIFEST.json"
    payload = json.dumps(manifest, indent=1, sort_keys=True) + "\n"
    out.write_text(payload, "utf-8", newline="\n")
    print(f"wrote {out}")
    print("manifest sha256:",
          hashlib.sha256(payload.encode()).hexdigest())


if __name__ == "__main__":
    main()
