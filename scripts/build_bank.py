"""Build a frozen scenario bank: generate seeds, run admission, freeze.

Usage: python scripts/build_bank.py --n 4 --out banks/v1.json
Admission rates are logged (design §12.3); the bank records both verdicts
(admitted_strict, admitted_v0) and ships scenarios passing admitted_v0,
with finding F-A documented in docs/SPEC_FINDINGS.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dataclasses import asdict                       # noqa: E402
from forge.scenarios.generate import generate, GENERATOR_VERSION  # noqa: E402
from forge.scenarios.admit import admit              # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--out", default="banks/v1.json")
    args = ap.parse_args()

    bank, log = [], []
    seed = 0
    while len(bank) < args.n:
        sc = generate(seed)
        checks = admit(sc)
        log.append({"seed": seed,
                    "admitted_strict": checks["admitted_strict"],
                    "admitted_v0": checks["admitted_v0"],
                    "profitable_exposure": checks["profitable_exposure"]})
        print(f"seed {seed}: strict={checks['admitted_strict']} "
              f"v0={checks['admitted_v0']}")
        if checks["admitted_v0"]:
            bank.append(asdict(sc))
        seed += 1
        if seed > args.n * 10:
            break

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "bank_version": "v1",
        "generator_version": GENERATOR_VERSION,
        "spec_finding_note": "admitted under admitted_v0; see docs/SPEC_FINDINGS.md F-A",
        "admission_log": log,
        "scenarios": bank,
    }, sort_keys=True), "utf-8")
    print(f"froze {len(bank)} scenarios -> {out}")


if __name__ == "__main__":
    main()
