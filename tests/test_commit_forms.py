"""Optional COMMIT tool forms (forge.runtime.commit_forms).

The default form must send tools.v1.json unchanged.  The pinned digests of
the two optional forms equal what the five-model clear-goal study's own
schema functions produce from the same tool file (checked by the owner
against the study code); scripts/verify_paper_data.py --five-model-replay
replays that study's 60 games through ModelAgent with these forms.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from forge.runtime import commit_forms as cf
from forge.runtime.agents import ModelAgent, corrective
from forge.runtime.config import ModelSpec
from forge.runtime.episode import run_episode
from forge.runtime.openrouter import CallResult
from forge.runtime.tools import load_tools
from forge.scenarios.bank import load_bank

from paper_variant_cases import ScriptedModelClient, read_jsonl

TOOLS_SHA256 = {
    "map": "46f517505953d0d0612428e3b659af5f1c3ce1d29670630ef6c2d9f25984b6c8",
    "nonempty-map": "618574cb8d00fdeeb02bd3a24f26d169ead9248c484b5393be9feb9a1cf12929",
    "entries": "4bfc1f55e4977e11dfae0eef03b6ad97b853df7de4963ed1d2c15131bf980819",
}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def slots_schema(tools: list) -> dict:
    (commit,) = [t for t in tools if t["function"]["name"] == "commit"]
    return commit["function"]["parameters"]["properties"]["slots"]


@pytest.mark.parametrize("form", cf.COMMIT_FORMS)
def test_tool_forms_are_pinned(form):
    assert digest(cf.commit_tools(load_tools(), form)) == TOOLS_SHA256[form]


def test_default_form_is_the_frozen_tool_file_and_nothing_is_mutated():
    before = json.dumps(load_tools(), sort_keys=True)
    assert cf.commit_tools(load_tools(), "map") is load_tools()
    for form in cf.COMMIT_FORMS:
        cf.commit_tools(load_tools(), form)
    assert json.dumps(load_tools(), sort_keys=True) == before


def test_optional_forms_change_only_commit_slots():
    base = load_tools()
    nonempty = cf.commit_tools(base, "nonempty-map")
    entries = cf.commit_tools(base, "entries")
    assert slots_schema(nonempty) == {**slots_schema(base), "minProperties": 1}
    assert slots_schema(entries)["type"] == "array"
    assert slots_schema(entries)["minItems"] == 1
    assert slots_schema(entries)["description"] == slots_schema(base)["description"]
    assert set(slots_schema(entries)["items"]["required"]) == {"slot_id", "value"}
    for tools in (nonempty, entries):
        others = [t for t in tools if t["function"]["name"] != "commit"]
        assert others == [t for t in base if t["function"]["name"] != "commit"]


def test_unknown_form_is_refused():
    with pytest.raises(ValueError):
        cf.check_commit_form("array")
    with pytest.raises(ValueError):
        ModelAgent(ModelSpec(slug="scripted/model"), None, commit_form="list")


def _reply(arguments) -> dict:
    return {"choices": [{"message": {"tool_calls": [
        {"id": "c0", "function": {"name": "commit", "arguments": arguments}}]}}]}


def _arguments(raw: dict):
    return raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]


def test_entries_convert_to_the_native_map():
    raw = _reply('{"slots": [{"slot_id": "M1", "value": "cursor"}, '
                 '{"slot_id": "M2", "value": "é"}]}')
    assert cf.entries_to_map(raw) is raw
    assert _arguments(raw) == '{"slots":{"M1":"cursor","M2":"é"}}'
    as_dict = _reply({"slots": [{"slot_id": "M1", "value": "x"}]})
    assert _arguments(cf.entries_to_map(as_dict)) == {"slots": {"M1": "x"}}


@pytest.mark.parametrize("arguments", [
    '{"slots": [{"slot_id": "M1", "value": "x"}, {"slot_id": "M1", "value": "y"}]}',
    '{"slots": [{"slot_id": "M1", "value": 3}]}',
    '{"slots": [{"slot_id": "M1", "value": "x", "extra": 1}]}',
    '{"slots": {"M1": "x"}}',
    "not json",
])
def test_malformed_or_native_commits_are_left_alone(arguments):
    raw = _reply(arguments)
    assert cf.entries_to_map(copy.deepcopy(raw)) == raw


def test_repair_sentence_only_after_an_empty_commit():
    msg = {"content": None, "tool_calls": [{"id": "c0", "function": {"name": "commit"}}]}
    empty = "illegal action: COMMIT needs slots: {slot_id -> value}"
    repaired = cf.repair_corrective(corrective(msg, empty), empty)
    assert repaired[1]["content"].endswith(cf.EMPTY_COMMIT_REPAIR)
    other = "illegal action: commit exactly the opening menu slots: ['M1']"
    assert cf.repair_corrective(corrective(msg, other), other) == corrective(msg, other)


class FormClient(ScriptedModelClient):
    """Answers COMMIT as entries when the tool schema asks for entries."""

    def __init__(self, scenario, *, empty_first_commit=False):
        super().__init__(scenario)
        self.tools: list[str] = []
        self.sent: list[list] = []
        self.empty_first_commit = empty_first_commit

    def chat(self, spec, messages, tools=None):
        self.tools.append(digest(tools))
        self.sent.append(messages)
        result = super().chat(spec, messages, tools)
        call = result.raw["choices"][0]["message"]["tool_calls"][0]["function"]
        if call["name"] == "commit":
            args = json.loads(call["arguments"])
            if self.empty_first_commit and len(messages) == 2:
                args["slots"] = {}
            elif slots_schema(tools)["type"] == "array":
                args["slots"] = [{"slot_id": k, "value": v} for k, v in args["slots"].items()]
            call["arguments"] = json.dumps(args)
        return result


def _play(sc, form, tmp_path, **client_kw):
    client = FormClient(sc, **client_kw)
    agents = {seat: ModelAgent(ModelSpec(slug="scripted/model"), client, commit_form=form)
              for seat in ("API", "DATA", "QA")}
    run_episode(sc, agents, tmp_path / form, bank="v1", episode_id=form)
    return client, read_jsonl(tmp_path / form / f"{form}.jsonl")


def _game(records: list) -> list:
    return [{k: v for k, v in r.items() if k != "utc"}
            for r in records if r["kind"] in ("event", "result")]


def test_forms_play_the_same_game(tmp_path):
    sc = load_bank("v1")[3]
    games = {form: _play(sc, form, tmp_path) for form in cf.COMMIT_FORMS}
    _, base = games["map"]
    assert any(r.get("kind") == "event" and r["action"]["name"] == "COMMIT" for r in base)
    for form, (client, records) in games.items():
        assert set(client.tools) == {TOOLS_SHA256[form]}
        assert _game(records) == _game(base)
        assert ("commit_form" in records[0]["seats"]["API"]) == (form != "map")
    # the entries reply is logged as the native map the engine saw
    _, entries = games["entries"]
    commits = [r for r in entries if r.get("kind") == "call"
               and r["raw"]["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "commit"]
    assert commits and all(_arguments(r["raw"]).startswith('{"slots":{') for r in commits)


def test_repair_reaches_the_model_only_with_an_optional_form(tmp_path):
    sc = load_bank("v1")[3]
    for form in cf.COMMIT_FORMS:
        client, _records = _play(sc, form, tmp_path, empty_first_commit=True)
        retries = [m for m in client.sent if len(m) > 2]
        assert retries
        repaired = [m for m in retries if m[-1]["content"].endswith(cf.EMPTY_COMMIT_REPAIR)]
        assert bool(repaired) == (form != "map")


def test_run_episode_refuses_a_commit_form_on_a_scripted_seat():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_episode.py"
    spec = importlib.util.spec_from_file_location("run_episode_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sc = load_bank("v1")[0]
    with pytest.raises(SystemExit):
        module.make_agent("scripted:cooperative", sc, None, None, "entries")
    assert module.parse_seat_values(["QA=entries"], "--commit-form", "FORM") == {"QA": "entries"}
    with pytest.raises(SystemExit):
        module.parse_seat_values(["XX=entries"], "--commit-form", "FORM")


def test_callresult_shape_is_what_the_replay_check_builds():
    raw = _reply('{"slots": {"M1": "x"}}')
    result = CallResult(raw=raw, provider=None, model="m", usage={}, cost_usd=None,
                        latency_s=0.0, attempts=1)
    assert result.message()["tool_calls"][0]["id"] == "c0"
