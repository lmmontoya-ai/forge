"""The optional paper variants (forge.variants) and reader views (forge.reader).

The golden test is the equivalence proof that travels with the repo: it
replays synthetic cases through this checkout and requires the outputs the
study repository's original implementation produced on the same cases
(tests/golden/paper_variants.json, written by
scripts/verify_variant_equivalence.py).
"""
import json
from pathlib import Path

import pytest

from forge.core import fold as fold_mod
from forge.render.panel import render_panel
from forge.render.render import render_prompt, render_user, system_block
from forge.runtime.agents import ModelAgent
from forge.runtime.config import ModelSpec
from forge.runtime.episode import run_episode
from forge.runtime.replay import decision_prompt, load_events
from forge.scenarios.bank import load_bank
from forge.variants import (PAPER_EXTENSION, extend_scenario, mover_reminder,
                            parse_mandate)
from forge.variants import clear_goal, hidden_priority as hp, inactive_label

from paper_variant_cases import FAMILIES, PortedBackend, ScriptedModelClient, compact, \
    compute_family, read_jsonl

GOLDEN = Path(__file__).parent / "golden" / "paper_variants.json"


@pytest.fixture(scope="module")
def bank():
    return load_bank("v1")


def test_registered_wording_digests():
    assert hp.wording_digest() == hp.REGISTERED_WORDING_DIGEST
    assert inactive_label.wording_digest() == inactive_label.REGISTERED_WORDING_DIGEST
    assert clear_goal.wording_digest() == clear_goal.REGISTERED_WORDING_DIGEST
    assert clear_goal.prove_sham_equivalence()["verdict"] == "PASS"


def test_menu_is_three_items_and_p_own_is_never_assignable():
    assert hp.PRIORITY_IDS == ("P_SHIP", "P_GUARD", "P_ALIGN")
    assert "P_OWN" in hp.PRIORITY_BY_ID
    for prefix in ("priority:", "clear-goal:"):
        with pytest.raises(ValueError):
            parse_mandate(prefix + "P_OWN")
    with pytest.raises(ValueError):
        parse_mandate("sham:TEAL")
    assert parse_mandate("principal") is None
    assert parse_mandate("own") is None


def test_axes_use_only_frozen_omega2_tokens():
    from forge.analysis.omega2 import OMEGA2_VOCABULARY
    for axis in hp.AXES:
        assert set(axis.numerator) <= set(OMEGA2_VOCABULARY)
        assert set(axis.denominator) <= set(OMEGA2_VOCABULARY)


def test_assignment_is_a_deterministic_permutation():
    one = hp.assign_priorities("episode-7", salt="s")
    assert one == hp.assign_priorities("episode-7", salt="s")
    assert sorted(one.values()) == sorted(hp.PRIORITY_IDS)
    assert set(one) == {"API", "DATA", "QA"}


def test_extension_is_the_paper_one(bank):
    sc = extend_scenario(bank[0])
    p = sc.params
    assert (p.D, p.tau_amend, p.run_budget, p.probe_budget, p.release_tokens) == \
        (72, 22, 20, 8, 4)
    assert PAPER_EXTENSION.scored_window() == range(1, 37)
    assert bank[0].params.D == 36          # the frozen bank is untouched


def test_extended_system_block_states_the_extended_deadline(bank):
    base, ext = bank[0], extend_scenario(bank[0])
    plain = system_block(base)
    extended = system_block(ext)
    assert b"- Turns: 36," in plain and b"- Turns: 72," in extended
    assert b"At turn 22 a spec addendum lands" in extended
    assert extended.replace(b"- Turns: 72,", b"- Turns: 36,") == plain
    state = fold_mod.initial_state(ext)
    assert "turn 1/72" in render_panel(state, [], "API")


@pytest.mark.parametrize("mandate", [
    "priority:P_SHIP", "priority:P_GUARD", "priority:P_ALIGN",
    "sham:COBALT", "clear-goal:P_ALIGN", "clear-sham:BRONZE"])
def test_variant_changes_only_the_mandate_paragraph(bank, mandate):
    sc = extend_scenario(bank[2])
    default = system_block(sc)
    variant = system_block(sc, mandate)
    head, _, rest = default.partition(b"## Mandate\n")
    vhead, _, vrest = variant.partition(b"## Mandate\n")
    assert head == vhead
    assert rest.partition(b"\n\n")[2] == vrest.partition(b"\n\n")[2]
    assert rest.partition(b"\n\n")[0] != vrest.partition(b"\n\n")[0]


def test_default_mandates_have_no_reminder():
    for mandate in ("principal", "own", "joint"):
        assert mover_reminder(mandate) is None
    assert mover_reminder("priority:P_GUARD").startswith(hp.REMINDER_HEADING)
    assert mover_reminder("clear-sham:MAROON").startswith(clear_goal.REMINDER_HEADING)


def test_model_agent_appends_the_reminder_but_logs_the_uninjected_digest(bank, tmp_path):
    sc = extend_scenario(bank[4])
    seen = []

    class Recorder(ScriptedModelClient):
        def chat(self, spec, messages, tools=None):
            seen.append(messages)
            return super().chat(spec, messages, tools)

    client = Recorder(sc)
    mandates = {"API": "priority:P_SHIP", "DATA": "priority:P_GUARD",
                "QA": "priority:P_ALIGN"}
    agents = {s: ModelAgent(ModelSpec(slug="scripted/model"), client, mandate=m)
              for s, m in mandates.items()}
    run_episode(sc, agents, tmp_path, bank="v1", episode_id="reminder")
    records = read_jsonl(tmp_path / "reminder.jsonl")
    events = load_events(records)
    first = next(r for r in records if r.get("kind") == "call")
    user = seen[0][1]["content"]
    assert user.endswith(hp.PRIORITY_BY_ID["P_SHIP"].reminder_line() + "\n")
    state = fold_mod.state_at(sc, events, 1)
    assert render_prompt(state, (), "API", mandate=mandates["API"])[1] == first["digest"]
    assert render_user(state, (), "API").rstrip() == user.rsplit("\n\n", 1)[0]
    meta = records[0]
    assert meta["seats"]["DATA"]["mandate"] == "priority:P_GUARD"
    # replay of the same decision sends the same bytes
    system, replay_user, _ = decision_prompt(sc, events, 1, mandate=mandates["API"])
    assert system.decode("utf-8") == seen[0][0]["content"]
    assert replay_user == user


def test_reader_views_do_not_leak_priority_wording(bank, tmp_path):
    from forge.reader.decision import build_decision_views
    from forge.reader.evidence import VIEW_PARTS
    sc = extend_scenario(bank[6])
    priorities = {"API": "P_ALIGN", "DATA": "P_SHIP", "QA": "P_GUARD"}
    agents = {s: ModelAgent(ModelSpec(slug="scripted/model"), ScriptedModelClient(sc),
                            mandate=f"priority:{p}") for s, p in priorities.items()}
    run_episode(sc, agents, tmp_path, bank="v1", episode_id="leak")
    records = read_jsonl(tmp_path / "leak.jsonl")
    events = load_events(records)
    views = build_decision_views(sc, events, records, predicted_tick=30,
                                 shuffle_salt="t", priorities=priorities)
    assert set(views.rendered) == set(VIEW_PARTS)
    corpus = hp.public_corpus(sc)
    public = {k: v for k, v in views.rendered.items() if k not in ("L4", "L4_full", "C_goal")}
    assert hp.audit_public_views(public, corpus=corpus, exempt=()) == {}
    # positive controls: the unredacted trace rung and C_goal do carry it
    target = priorities[fold_mod.state_at(sc, events, 30).mover]
    priority = hp.PRIORITY_BY_ID[target]
    assert hp.audit_public_view(views.rendered["L4_full"], priority)
    assert hp.audit_public_view(views.rendered["C_goal"], priority)


def test_golden_paper_variants_reproduce(tmp_path):
    golden = json.loads(GOLDEN.read_text("utf-8"))
    backend = PortedBackend()
    for family in FAMILIES:
        ours = compact(compute_family(backend, family, tmp_path / family))
        assert ours == golden["families"][family], family
