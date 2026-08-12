"""Pre-canary handshake: ONE forced tool call per model on the real tick-1
prompt and tool payload.  Verifies, per model, before any episode money:
  - the pinned provider actually serves the call (single-provider rule),
  - tool_choice=required is accepted alongside the reasoning config,
  - the reply parses into a legal FORGE action,
  - finish_reason is not 'length'.
Cost: cents.  Usage: python scripts/preflight.py --models models.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.core import actions as actions_mod                # noqa: E402
from forge.core import fold as fold_mod                      # noqa: E402
from forge.render.render import render_user, system_block    # noqa: E402
from forge.runtime.agents import parse_reply                 # noqa: E402
from forge.runtime.config import load_models                 # noqa: E402
from forge.runtime.openrouter import OpenRouterClient, CostMeter  # noqa: E402
from forge.runtime.tools import load_tools                   # noqa: E402
from forge.scenarios.bank import load_bank                   # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models.json")
    ap.add_argument("--bank", default="v1")
    args = ap.parse_args()

    sc = load_bank(args.bank)[0]
    st = fold_mod.initial_state(sc)
    messages = [
        {"role": "system", "content": system_block(sc).decode("utf-8")},
        {"role": "user", "content": render_user(st, [], "API")},
    ]
    tools = load_tools()
    client = OpenRouterClient()
    meter = CostMeter(cap_usd=1.0)

    ok_all = True
    for name, spec in load_models(args.models).items():
        try:
            result = client.chat(spec, messages, tools)
            meter.add(result, spec)
            action, error, _ = parse_reply(result)
            legal = action is not None and \
                actions_mod.validate(st, "API", action) is None
            pin_ok = (not spec.provider_order
                      or result.provider in (None, *spec.provider_order))
            print(f"{name:10} provider={result.provider!r:20} "
                  f"finish={result.finish_reason()!r:12} "
                  f"action={(action.name if action else error)!r:30} "
                  f"legal={legal} pin_ok={pin_ok}")
            ok_all &= legal and pin_ok
        except Exception as e:                                # noqa: BLE001
            print(f"{name:10} FAILED: {e}")
            ok_all = False
    print(f"\nspent ~${meter.spent_usd:.4f} across {meter.calls} calls"
          f" ({meter.unpriced_calls} unpriced)")
    print("PREFLIGHT", "PASS" if ok_all else "FAIL")


if __name__ == "__main__":
    main()
