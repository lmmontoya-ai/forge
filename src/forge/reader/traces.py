"""Reasoning-trace classification and the trace-rung source firewall.

A reader view may quote the target's own earlier reasoning (the L4 rungs
in `forge.reader.evidence`).  This module decides, from logged provider
calls alone, which earlier calls are eligible to be quoted and how
readable their reasoning is.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class TraceKind(str, Enum):
    FULL = "full_readable_reasoning"
    SUMMARY = "readable_reasoning_summary"
    ENCRYPTED = "encrypted_only"
    MISSING = "missing"
    INVALID = "invalid_or_no_action"


@dataclass(frozen=True)
class ActingTrace:
    tick: int
    seat: str
    kind: TraceKind
    text: str | None
    provider: str | None
    served_model: str | None
    attempt: int
    action: str | None

    @property
    def readable(self) -> bool:
        return self.kind in {TraceKind.FULL, TraceKind.SUMMARY} and bool(self.text)


def _message(record: dict) -> dict:
    try:
        return record["raw"]["choices"][0]["message"] or {}
    except (KeyError, IndexError, TypeError):
        return {}


def _has_action(message: dict) -> bool:
    calls = message.get("tool_calls") or []
    return any((call.get("function") or {}).get("name") for call in calls)


def _action_name(message: dict) -> str | None:
    calls = message.get("tool_calls") or []
    names = [(call.get("function") or {}).get("name") for call in calls]
    return str(next((name for name in names if name), "")).upper() or None


def classify_call(record: dict) -> ActingTrace:
    """Classify one call conservatively; summaries never become full traces."""
    message = _message(record)
    base = dict(
        tick=int(record.get("tick", -1)),
        seat=str(record.get("seat", "")),
        provider=record.get("provider") or record.get("raw", {}).get("provider"),
        served_model=record.get("served_model") or record.get("raw", {}).get("model"),
        attempt=int(record.get("attempt", 0)),
        action=_action_name(message),
    )
    finish = (record.get("raw", {}).get("choices") or [{}])[0].get("finish_reason")
    if record.get("error") or finish == "length" or not _has_action(message):
        return ActingTrace(kind=TraceKind.INVALID, text=None, **base)

    details = message.get("reasoning_details") or []
    full = [str(detail.get("text", "")).strip() for detail in details
            if detail.get("type") == "reasoning.text" and detail.get("text")]
    summaries = [str(detail.get("summary", "")).strip() for detail in details
                 if detail.get("type") == "reasoning.summary" and detail.get("summary")]
    encrypted = any(detail.get("type") == "reasoning.encrypted" for detail in details)
    if full:
        return ActingTrace(kind=TraceKind.FULL, text="\n".join(full), **base)
    if summaries:
        return ActingTrace(kind=TraceKind.SUMMARY, text="\n".join(summaries), **base)

    # Untyped provider `reasoning` is readable, but its provenance cannot
    # establish that it is a full hidden trace.  Treat it as a summary.
    fallback = message.get("reasoning")
    if isinstance(fallback, str) and fallback.strip():
        return ActingTrace(kind=TraceKind.SUMMARY, text=fallback.strip(), **base)
    if encrypted:
        return ActingTrace(kind=TraceKind.ENCRYPTED, text=None, **base)
    return ActingTrace(kind=TraceKind.MISSING, text=None, **base)


def prior_acting_traces(
    records: Iterable[dict],
    *,
    target_seat: str,
    predicted_tick: int,
    accepted_actions: Mapping[int, str] | None = None,
) -> list[ActingTrace]:
    """Return at most one successful prior acting trace per target tick.

    The filter is the firewall: episode-log calls only, purpose exactly
    `act`, target seat, tick strictly before T, successful action-producing
    attempt.  Replay or forecast calls and rejected corrective attempts are
    structurally ineligible.
    """
    eligible: dict[int, ActingTrace] = {}
    for record in records:
        if record.get("kind") != "call" or record.get("purpose") != "act":
            continue
        if record.get("seat") != target_seat:
            continue
        tick = int(record.get("tick", -1))
        if tick >= predicted_tick:
            continue
        trace = classify_call(record)
        if trace.kind == TraceKind.INVALID:
            continue
        if accepted_actions is not None:
            accepted = accepted_actions.get(tick)
            if accepted is None or trace.action != str(accepted).upper():
                continue
        previous = eligible.get(tick)
        if previous is None or trace.attempt > previous.attempt:
            eligible[tick] = trace
    return [eligible[tick] for tick in sorted(eligible)]


def trace_coverage(traces: Iterable[ActingTrace]) -> dict[str, int | float]:
    values = list(traces)
    counts = {kind.value: sum(trace.kind == kind for trace in values) for kind in TraceKind}
    readable = counts[TraceKind.FULL.value] + counts[TraceKind.SUMMARY.value]
    return {**counts, "total": len(values),
            "readable_rate": readable / len(values) if values else 0.0}
