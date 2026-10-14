"""Run one episode: at zero cost with scripted seats, or with models.

Usage (zero cost, no API key):
  python scripts/run_episode.py --bank v1 --index 0 \
      --api scripted:cooperative --data scripted:cooperative \
      --qa scripted:cooperative --out data/runs/smoke

Usage (models via OpenRouter; needs OPENROUTER_API_KEY and a models.json,
see models.example.json):
  python scripts/run_episode.py --bank v1 --index 0 --models models.json \
      --api model:luna --data model:sonnet --qa model:grok \
      --extended --mandate API=priority:P_SHIP --mandate DATA=priority:P_GUARD \
      --mandate QA=priority:P_ALIGN --budget-usd 5 --out data/runs/v2

Scripted policies: cooperative, saboteur, silent, over-reporter,
probe-hoarder, class-banker, early-banker (forge.policies.scripted.PLANS).
Mandates (model seats only): principal (default), own, joint, or a
forge.variants mandate such as priority:P_SHIP, sham:COBALT,
clear-goal:P_ALIGN, clear-sham:BRONZE.  --extended plays the paper's
D=72 episode (forge.variants.PAPER_EXTENSION).
--commit-form SEAT=FORM (model seats only) sends that seat an optional
COMMIT tool schema: map (default), nonempty-map or entries
(forge.runtime.commit_forms).
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

SEATS = ("API", "DATA", "QA")


def make_agent(spec_str: str, sc, models_path: str | None, mandate: str | None,
               commit_form: str | None = None):
    kind, _, name = spec_str.partition(":")
    if kind == "scripted":
        if mandate is not None:
            raise SystemExit(f"--mandate applies only to model seats, not {spec_str!r}")
        if commit_form is not None:
            raise SystemExit(f"--commit-form applies only to model seats, not {spec_str!r}")
        plan = PLANS[name](sc)
        return ScriptedAgent(name, plan_policy(plan))
    if kind == "model":
        from forge.render.render import system_block
        from forge.runtime.config import load_models
        from forge.runtime.commit_forms import DEFAULT_COMMIT_FORM, check_commit_form
        from forge.runtime.openrouter import OpenRouterClient
        system_block(sc, mandate or "principal")      # refuse a bad mandate before any call
        try:
            form = check_commit_form(commit_form or DEFAULT_COMMIT_FORM)
        except ValueError as error:
            raise SystemExit(str(error))
        spec = load_models(models_path or "models.json")[name]
        return ModelAgent(spec, OpenRouterClient(), mandate=mandate or "principal",
                          commit_form=form)
    raise SystemExit(f"unknown agent spec {spec_str!r}")


def parse_seat_values(values: list[str], flag: str, what: str) -> dict[str, str]:
    out = {}
    for value in values:
        seat, sep, item = value.partition("=")
        if not sep or seat not in SEATS:
            raise SystemExit(f"{flag} expects SEAT={what} with SEAT in {SEATS}, got {value!r}")
        out[seat] = item
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="v1")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--api", default="scripted:cooperative")
    ap.add_argument("--data", default="scripted:cooperative")
    ap.add_argument("--qa", default="scripted:cooperative")
    ap.add_argument("--models", default=None)
    ap.add_argument("--mandate", action="append", default=[], metavar="SEAT=MANDATE")
    ap.add_argument("--commit-form", action="append", default=[], metavar="SEAT=FORM",
                    help="optional COMMIT tool schema for a model seat: map (default), "
                         "nonempty-map or entries")
    ap.add_argument("--extended", action="store_true",
                    help="play the paper's extended episode (D=72, budgets doubled)")
    ap.add_argument("--budget-usd", type=float, default=None,
                    help="spend cap for model seats (refuses new calls once reached)")
    ap.add_argument("--episode-id", default=None)
    ap.add_argument("--out", default="data/runs/smoke")
    args = ap.parse_args()

    sc = load_bank(args.bank)[args.index]
    if args.extended:
        from forge.variants import extend_scenario
        sc = extend_scenario(sc)
    mandates = parse_seat_values(args.mandate, "--mandate", "MANDATE")
    forms = parse_seat_values(args.commit_form, "--commit-form", "FORM")
    specs = {"API": args.api, "DATA": args.data, "QA": args.qa}
    agents = {seat: make_agent(specs[seat], sc, args.models, mandates.get(seat),
                               forms.get(seat))
              for seat in SEATS}
    meter = None
    if args.budget_usd is not None:
        from forge.runtime.openrouter import CostMeter
        meter = CostMeter(cap_usd=args.budget_usd)
    result = run_episode(sc, agents, args.out, bank=args.bank, meter=meter,
                         episode_id=args.episode_id)
    print(result)


if __name__ == "__main__":
    main()
