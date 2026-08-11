"""Model registry: what a 'model' is for a FORGE study — the pair
(slug, pinned serving provider), imported from the LEDGER plan §3.8."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    slug: str
    label: str = ""
    provider_order: tuple = ()
    temperature: float = 1.0
    max_tokens: int = 16000        # generous: WRITE content + native reasoning
    reasoning: dict | None = None
    tool_choice: str = "required"
    price_in: float | None = None
    price_out: float | None = None

    def describe(self) -> dict:
        return {
            "slug": self.slug, "label": self.label or self.slug,
            "provider_order": list(self.provider_order),
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "reasoning": self.reasoning, "tool_choice": self.tool_choice,
        }


def load_models(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text("utf-8"))
    out = {}
    for name, m in payload["models"].items():
        out[name] = ModelSpec(
            slug=m["slug"], label=m.get("label", name),
            provider_order=tuple(m.get("provider_order", [])),
            temperature=m.get("temperature", 1.0),
            max_tokens=m.get("max_tokens", 16000),
            reasoning=m.get("reasoning"),
            tool_choice=m.get("tool_choice", "required"),
            price_in=m.get("price_in"), price_out=m.get("price_out"),
        )
    return out
