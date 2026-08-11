"""Smoke-run an episode at zero cost with scripted seats, or with models.

Usage:
  python scripts/run_episode.py --bank v1 --index 0 \
      --api scripted:cooperative --data scripted:cooperative \
      --qa scripted:cooperative --out data/runs/smoke
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.scenarios.bank import load_bank                    # noqa: E402
from forge.policies.scripted import PLANS, plan_policy        # noqa: E402
from forge.runtime.agents import ScriptedAgent, ModelAgent    # noqa: E402
from forge.runtime.episode import run_episode                 # noqa: E402


def make_agent(spec_str: str, sc, models_path: str | None):
    kind, _, name = spec_str.partition(":")
    if kind == "scripted":
        plan = PLANS[name](sc)
        return ScriptedAgent(name, plan_policy(plan))
    if kind == "model":
        from forge.runtime.config import load_models
        from forge.runtime.openrouter import OpenRouterClient
        spec = load_models(models_path or "models.json")[name]
        return ModelAgent(spec, OpenRouterClient())
    raise SystemExit(f"unknown agent spec {spec_str!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="v1")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--api", default="scripted:cooperative")
    ap.add_argument("--data", default="scripted:cooperative")
    ap.add_argument("--qa", default="scripted:cooperative")
    ap.add_argument("--models", default=None)
    ap.add_argument("--out", default="data/runs/smoke")
    args = ap.parse_args()

    sc = load_bank(args.bank)[args.index]
    agents = {"API": make_agent(args.api, sc, args.models),
              "DATA": make_agent(args.data, sc, args.models),
              "QA": make_agent(args.qa, sc, args.models)}
    result = run_episode(sc, agents, args.out, bank=args.bank)
    print(result)


if __name__ == "__main__":
    main()
