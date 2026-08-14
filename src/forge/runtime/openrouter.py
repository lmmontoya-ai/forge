"""The only code that talks to a provider (via OpenRouter), ported from
LEDGER unchanged in discipline: provider errors, timeouts, and filter
failures are infrastructure, never behavior; retried with backoff; past the
wall-clock cap the episode is abandoned and quarantined.  A response whose
finish_reason is 'length' is a configuration failure (the reasoning budget
hit max_tokens), also never behavior: it is retried and, persisting,
abandons the call.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from .config import ModelSpec

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRYABLE = {408, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    pass


class EpisodeAbandoned(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class CallResult:
    raw: dict
    provider: str | None
    model: str
    usage: dict
    cost_usd: float | None
    latency_s: float
    attempts: int

    def message(self) -> dict:
        return (self.raw.get("choices") or [{}])[0].get("message") or {}

    def finish_reason(self) -> str | None:
        return (self.raw.get("choices") or [{}])[0].get("finish_reason")


class CostMeter:
    """Thread-safe: one meter may guard several concurrent episodes."""

    def __init__(self, cap_usd: float | None = None):
        import threading
        self.cap_usd = cap_usd
        self.spent_usd = 0.0
        self.calls = 0
        self.unpriced_calls = 0
        self._lock = threading.Lock()

    def check(self) -> None:
        """Refuse a new call once prior completed calls have exhausted the cap."""
        with self._lock:
            if self.cap_usd is not None and self.spent_usd >= self.cap_usd:
                raise BudgetExceeded(
                    f"spent ${self.spent_usd:.2f} >= cap ${self.cap_usd:.2f}"
                )

    def add(self, result: CallResult, spec: ModelSpec) -> None:
        with self._lock:
            self._add(result, spec)

    def _add(self, result: CallResult, spec: ModelSpec) -> None:
        self.calls += 1
        cost = result.cost_usd
        if cost is None and spec.price_in is not None and spec.price_out is not None:
            u = result.usage or {}
            cost = (u.get("prompt_tokens", 0) * spec.price_in
                    + u.get("completion_tokens", 0) * spec.price_out) / 1e6
        if cost is None:
            self.unpriced_calls += 1
            cost = 0.0
        self.spent_usd += cost
        if self.cap_usd is not None and self.spent_usd > self.cap_usd:
            raise BudgetExceeded(
                f"spent ${self.spent_usd:.2f} > cap ${self.cap_usd:.2f} "
                f"after {self.calls} calls")


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, *, session=None,
                 timeout_s: float = 300.0, max_attempts: int = 6,
                 wall_clock_cap_s: float = 1200.0, app_name: str = "forge"):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ProviderError(
                "no API key: pass api_key or set OPENROUTER_API_KEY")
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.timeout_s = timeout_s
        self.max_attempts = max_attempts
        self.wall_clock_cap_s = wall_clock_cap_s
        self.app_name = app_name

    def _body(self, spec: ModelSpec, messages, tools) -> dict:
        body = {
            "model": spec.slug,
            "messages": messages,
            "temperature": spec.temperature,
            "max_tokens": spec.max_tokens,
            "usage": {"include": True},
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = spec.tool_choice
            # FORGE permits exactly one action per turn. This provider-level
            # control prevents a model from proposing a parallel action bundle.
            body["parallel_tool_calls"] = False
        if spec.provider_order:
            body["provider"] = {"order": list(spec.provider_order),
                                "allow_fallbacks": False}
        if spec.reasoning is not None:
            body["reasoning"] = spec.reasoning
        return body

    def chat(self, spec: ModelSpec, messages, tools=None) -> CallResult:
        import requests
        body = self._body(spec, messages, tools)
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "X-Title": self.app_name}
        started = time.monotonic()
        last_err = "no attempt made"
        for attempt in range(1, self.max_attempts + 1):
            if time.monotonic() - started > self.wall_clock_cap_s:
                break
            t0 = time.monotonic()
            try:
                resp = self.session.post(BASE_URL, json=body, headers=headers,
                                         timeout=self.timeout_s)
            except requests.RequestException as e:
                last_err = f"transport: {e}"
                time.sleep(min(2 ** attempt, 30))
                continue
            latency = time.monotonic() - t0
            if resp.status_code in RETRYABLE:
                last_err = f"HTTP {resp.status_code}"
                time.sleep(min(2 ** attempt, 30))
                continue
            if resp.status_code != 200:
                raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            try:
                raw = resp.json()
            except json.JSONDecodeError:
                last_err = "unparseable 200 body"
                time.sleep(min(2 ** attempt, 30))
                continue
            err = raw.get("error")
            if err:
                code = err.get("code")
                if isinstance(code, int) and code in RETRYABLE:
                    last_err = f"provider error {code}: {err.get('message')}"
                    time.sleep(min(2 ** attempt, 30))
                    continue
                raise ProviderError(f"provider error: {err}")
            result = CallResult(
                raw=raw, provider=raw.get("provider"),
                model=raw.get("model", spec.slug),
                usage=raw.get("usage") or {},
                cost_usd=(raw.get("usage") or {}).get("cost"),
                latency_s=round(latency, 3), attempts=attempt)
            if result.finish_reason() == "length":
                # configuration failure, never behavior: retry, then abandon
                last_err = "finish_reason=length (raise max_tokens)"
                continue
            return result
        raise EpisodeAbandoned(
            f"provider unavailable past caps ({last_err}); "
            "episode abandoned and quarantined")
