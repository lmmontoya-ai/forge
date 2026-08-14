"""Runtime plumbing, episode integration, admission on the frozen bank."""
import json
from pathlib import Path

import pytest

from forge.game import Game
from forge.policies.scripted import PLANS, cooperative_plan, plan_policy
from forge.runtime.agents import ModelAgent, ScriptedAgent, parse_reply, corrective
from forge.runtime.config import ModelSpec
from forge.runtime.episode import run_episode
from forge.runtime.openrouter import BudgetExceeded, CallResult, CostMeter, OpenRouterClient
from forge.runtime.replay import load_events, sample_policy
from forge.runtime.tools import action_from_tool_call, load_tools
from forge.scenarios.bank import load_bank

from conftest import run_plan


def test_tools_cover_all_actions():
    tools = load_tools()
    names = {t["function"]["name"] for t in tools}
    assert names == {"commit", "read", "write", "run", "probe", "release",
                     "propose_iface", "agree", "report", "query", "inform",
                     "wait", "refuse"}


def test_openrouter_disables_parallel_tool_calls():
    spec = ModelSpec(slug="m", reasoning={"effort": "high"})
    client = OpenRouterClient(api_key="test")
    with_tools = client._body(spec, [{"role": "user", "content": "x"}], load_tools())
    without_tools = client._body(spec, [{"role": "user", "content": "x"}], None)
    assert with_tools["parallel_tool_calls"] is False
    assert "parallel_tool_calls" not in without_tools


def test_action_from_tool_call_roundtrip():
    a = action_from_tool_call("write", '{"path": "api.py", "content": "x"}')
    assert a.name == "WRITE" and a.args["path"] == "api.py"
    try:
        action_from_tool_call("hack", "{}")
        assert False
    except ValueError:
        pass


def _fake_result(message, *, cost_usd=None):
    return CallResult(raw={"choices": [{"message": message}]}, provider="p",
                      model="m", usage={"cost": cost_usd} if cost_usd else {},
                      cost_usd=cost_usd, latency_s=0.0,
                      attempts=1)


def test_parse_reply_and_corrective_shapes():
    ok = _fake_result({"tool_calls": [{"id": "c1", "function": {
        "name": "wait", "arguments": "{}"}}]})
    action, error, msg = parse_reply(ok)
    assert action is not None and action.name == "WAIT"
    prose = _fake_result({"content": "I think we should talk."})
    action, error, msg = parse_reply(prose)
    assert action is None
    fix = corrective(msg, error)
    assert fix[0]["role"] == "assistant" and fix[1]["role"] == "user"

    multiple = _fake_result({"tool_calls": [
        {"id": "c1", "function": {"name": "wait", "arguments": "{}"}},
        {"id": "c2", "function": {"name": "run", "arguments": "{}"}},
    ]})
    action, error, _ = parse_reply(multiple)
    assert action is None
    assert error == "reply contained 2 tool calls; exactly one is required"


def test_policy_replay_extra_user_line_is_optional_and_non_mutating(sc):
    class CaptureClient:
        def __init__(self):
            self.messages = []

        def chat(self, _spec, messages, _tools):
            self.messages.append(messages)
            return _fake_result({"tool_calls": [{"id": "c1", "function": {
                "name": "wait", "arguments": "{}"}}]})

    plain = CaptureClient()
    injected = CaptureClient()
    plain_batch = sample_policy(plain, object(), sc, [], 1, n=1)
    injected_batch = sample_policy(injected, object(), sc, [], 1, n=1,
                                   extra_user_line="forecast: DATA likely READ")
    plain_user = plain.messages[0][-1]["content"]
    injected_user = injected.messages[0][-1]["content"]
    assert injected_user == plain_user.rstrip() + \
        "\n\nforecast: DATA likely READ\n"
    assert plain_batch.digest != injected_batch.digest


def test_sample_policy_reports_each_completed_draw():
    sc = load_bank()[0]

    class CaptureClient:
        def chat(self, spec, messages, tools):
            return _fake_result({"tool_calls": [{"id": "c1", "function": {
                "name": "wait", "arguments": "{}"}}]})

    completed = []
    sample_policy(
        CaptureClient(), object(), sc, [], 1, n=3, parallel=2,
        on_draw=lambda index, action, records, providers: completed.append(
            (index, action.name if action else None, len(records), len(providers))
        ),
    )
    assert sorted(completed) == [(0, "WAIT", 1, 1), (1, "WAIT", 1, 1), (2, "WAIT", 1, 1)]


def test_over_cap_replay_reports_the_charged_draw_before_stopping():
    sc = load_bank()[0]

    class CaptureClient:
        def chat(self, spec, messages, tools):
            return _fake_result({"tool_calls": [{"id": "c1", "function": {
                "name": "wait", "arguments": "{}"}}]}, cost_usd=0.2)

    completed = []
    meter = CostMeter(cap_usd=0.1)
    with pytest.raises(BudgetExceeded):
        sample_policy(
            CaptureClient(), object(), sc, [], 1, n=1, meter=meter,
            on_draw=lambda index, action, records, providers: completed.append(
                (index, action.name if action else None, len(records))
            ),
        )
    assert completed == [(0, "WAIT", 1)]
    assert meter.spent_usd == pytest.approx(0.2)
    with pytest.raises(BudgetExceeded):
        meter.check()


def test_over_cap_episode_logs_charged_call_before_abandoning(sc, tmp_path):
    class CaptureClient:
        def chat(self, spec, messages, tools):
            return _fake_result({"tool_calls": [{"id": "c1", "function": {
                "name": "wait", "arguments": "{}"}}]}, cost_usd=0.2)

    spec = ModelSpec(slug="m", provider_order=("p",))
    agents = {seat: ModelAgent(spec, CaptureClient()) for seat in ("API", "DATA", "QA")}
    result = run_episode(sc, agents, tmp_path, bank="v1", meter=CostMeter(cap_usd=0.1))
    assert result is None
    records = [
        json.loads(line) for line in next(tmp_path.glob("*.jsonl")).read_text("utf-8").splitlines()
    ]
    assert [row["kind"] for row in records].count("call") == 1
    assert any(row["kind"] == "abandoned" for row in records)
    assert not any(row["kind"] == "event" for row in records)
    assert next(row for row in records if row["kind"] == "call")["usage"]["cost"] == 0.2


def test_full_episode_with_logger(sc, tmp_path):
    agents = {s: ScriptedAgent("cooperative",
                               plan_policy(cooperative_plan(sc)))
              for s in ("API", "DATA", "QA")}
    result = run_episode(sc, agents, tmp_path, bank="v1")
    assert result is not None and result["J"] >= 95
    log_file = next(tmp_path.glob("*.jsonl"))
    records = [json.loads(line) for line in
               log_file.read_text("utf-8").splitlines()]
    kinds = [r["kind"] for r in records]
    assert kinds[0] == "meta" and "result" in kinds
    events = load_events(records)
    assert len(events) == sc.params.D
    # the event log alone reconstructs the world: replay digest = original
    from forge.core import fold as fold_mod
    from forge.render.render import render_prompt
    st = fold_mod.state_at(sc, events, 17)
    prefix = [e for e in events if e.tick < 17]
    g = Game(sc)
    for e in prefix:
        g.play(e.action, invalid=e.invalid)
    d_live = render_prompt(g.state, g.events, st.mover)[1]
    d_replay = render_prompt(st, prefix, st.mover)[1]
    assert d_live == d_replay


def test_all_scripted_plans_terminate(sc):
    for name, plan_fn in PLANS.items():
        game = run_plan(sc, plan_fn(sc))
        assert game.over, name
        assert game.result is not None


def test_bank_admission_recorded():
    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "banks" / "v1.json")
        .read_text("utf-8"))
    assert payload["scenarios"], "bank is empty"
    for entry in payload["admission_log"]:
        assert entry["admitted_v0"], entry
    # F-A finding must stay visible until resolved
    assert "SPEC_FINDINGS" in payload["spec_finding_note"]


def test_every_bank_scenario_distinct():
    bank = load_bank("v1")
    ids = [sc.scenario_id for sc in bank]
    assert len(set(ids)) == len(ids)
    facts = [sc.fragments["API"] for sc in bank]
    assert len(set(facts)) > 1


def test_over_reporter_claims_graded(sc):
    from forge.grading.reports import grade_report
    from forge.core import fold as fold_mod
    game = run_plan(sc, PLANS["over-reporter"](sc))
    ev = [e for e in game.events if e.action.name == "REPORT"][0]
    st = fold_mod.state_at(sc, game.events, ev.tick)
    graded = grade_report(st, ev.action.args["claims"])
    assert {g["true"] for g in graded} == {False} or \
        any(g["true"] is False for g in graded)
