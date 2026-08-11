"""Run one episode end to end.  An abandoned episode writes an abandonment
record and no result record: quarantined, never truncated into fake
behavior.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from ..core.events import Action
from ..game import Game, IllegalAction
from ..scenarios.generate import GENERATOR_VERSION
from .log import EpisodeLogger
from .openrouter import BudgetExceeded, EpisodeAbandoned
from .tools import SPEC_PATH


def _code_version() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5,
                              cwd=Path(__file__).parent).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def run_episode(scenario, agents: dict, out_dir: str | Path, *,
                bank: str | None = None, meter=None,
                episode_id: str | None = None) -> dict | None:
    episode_id = episode_id or uuid.uuid4().hex[:12]
    tools_version = json.loads(SPEC_PATH.read_text("utf-8"))["spec_version"]
    logger = EpisodeLogger(Path(out_dir) / f"{episode_id}.jsonl", {
        "episode_id": episode_id, "bank": bank,
        "scenario_id": scenario.scenario_id, "seed": scenario.seed,
        "seats": {s: a.describe() for s, a in agents.items()},
        "generator_version": GENERATOR_VERSION,
        "tools_version": tools_version,
        "code_version": _code_version(),
    })
    g = Game(scenario)
    try:
        while not g.over:
            seat = g.turn
            action = agents[seat].act(g, seat, logger, meter)
            invalid = bool(action.args.pop("__invalid__", False)) \
                if action.name == "WAIT" else False
            try:
                ev = g.play(action, invalid=invalid)
            except IllegalAction as e:
                logger.write({"kind": "anomaly", "tick": g.state.tick + 1,
                              "seat": seat, "rejected": action.name,
                              "reason": str(e)})
                ev = g.play(Action("WAIT", {}), invalid=True)
            logger.event(ev.tick, seat, ev.action, invalid=ev.invalid,
                         truncated=ev.truncated)
        r = g.result
        logger.result(dict(r))
        return r
    except (EpisodeAbandoned, BudgetExceeded) as e:
        logger.abandon(str(e))
        return None
    finally:
        if meter is not None:
            logger.write({"kind": "spend", "calls": meter.calls,
                          "spent_usd": round(meter.spent_usd, 4),
                          "unpriced_calls": meter.unpriced_calls})
        logger.close()
