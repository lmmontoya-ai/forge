"""Append-only JSONL episode logging (LEDGER plan §3.8 schema, adapted):
one meta record, one record per ledger event, one per provider call with
the raw response verbatim, a final result record.  The event log alone
reconstructs the world byte-for-byte; call records preserve what the model
actually sampled.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class EpisodeLogger:
    def __init__(self, path: str | Path, meta: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a", encoding="utf-8")
        self.write({"kind": "meta", **meta})

    def write(self, record: dict) -> None:
        record = {**record, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime())}
        self._f.write(json.dumps(record, default=str) + "\n")
        self._f.flush()

    def event(self, tick: int, seat: str, action, *, invalid=False,
              truncated=False) -> None:
        self.write({"kind": "event", "tick": tick, "seat": seat,
                    "action": {"name": action.name, "args": action.args},
                    "invalid": invalid, "truncated": truncated})

    def call(self, **kw) -> None:
        result = kw.pop("result", None)
        rec = {"kind": "call", **kw}
        if result is not None:
            rec.update({"raw": result.raw, "provider": result.provider,
                        "served_model": result.model, "usage": result.usage,
                        "latency_s": result.latency_s,
                        "transport_attempts": result.attempts})
        self.write(rec)

    def result(self, result: dict) -> None:
        self.write({"kind": "result", **result})

    def abandon(self, reason: str) -> None:
        self.write({"kind": "abandoned", "reason": reason})

    def close(self) -> None:
        self._f.close()
