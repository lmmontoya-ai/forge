"""Frozen prompt digests of two reader studies in the report, and the code
that rebuilds them.

tests/golden/ordinary_panel_forge.json holds the Engineering prompts of the
nine-forecaster ordinary-play panel (64 decisions of the v1 trio campaign,
views B0 and L3).  tests/golden/v2_objective_inference.json holds the goal
naming prompts (stage S3 of the hidden-priority campaign, 384 cells).  Both
were copied from the study's records.  Rebuilding a recorded digest needs
the campaign's trajectories, which hold model-written text and are not
shipped, so that comparison is scripts/verify_paper_data.py
(--ordinary-panel, --v2-campaign).  These tests check what needs no private
data: the files' shape, every panel system block, the S3 wording, and the
check script itself on a synthetic campaign.
"""
import hashlib
import importlib.util
import itertools
import json
from collections import Counter
from pathlib import Path

import pytest

from forge.core import fold as fold_mod
from forge.core.events import SEATS
from forge.reader.decision import build_decision_views, forecast_system_block
from forge.reader.evidence import PREDICTION_TASK, render_view
from forge.reader import objective as ob
from forge.runtime.agents import ModelAgent
from forge.runtime.config import ModelSpec
from forge.runtime.episode import run_episode
from forge.runtime.replay import load_events
from forge.scenarios.bank import load_bank
from forge.variants import extend_scenario
from forge.variants.hidden_priority import PRIORITY_IDS

from paper_variant_cases import ScriptedModelClient, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
PANEL = json.loads((ROOT / "tests" / "golden" / "ordinary_panel_forge.json").read_text("utf-8"))
OBJECTIVE = json.loads((ROOT / "tests" / "golden" / "v2_objective_inference.json").read_text("utf-8"))

#: sha256 of OBJECTIVE_MANDATE + objective_task for the six menu orders;
#: equal to the study's own wording (checked by the owner against its code).
OBJECTIVE_WORDING_SHA256 = "d296724fdab5902861a18e9609e6d7927f4092627a7a4d41982d8be2e7231567"


def sha(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def canonical_sha(value) -> str:
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


@pytest.fixture(scope="module")
def verify():
    spec = importlib.util.spec_from_file_location(
        "verify_paper_data", ROOT / "scripts" / "verify_paper_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ panel golden
def test_panel_golden_shape():
    positions = PANEL["positions"]
    assert PANEL["panel_cells"] == 1152 and PANEL["forecasters"] == 9
    assert PANEL["shuffle_salt"] == "ordinary-prediction-panel:v1"
    assert PANEL["views"] == {"situation": "B0", "full_record": "L3"}
    assert len(positions) == 64
    assert PANEL["panel_cells"] == len(positions) * 2 * PANEL["forecasters"]
    assert len({p["position_id"] for p in positions}) == 64
    assert len({p["episode_id"] for p in positions}) == 23
    assert Counter(p["target"] for p in positions) == {"grok": 22, "luna": 21, "sonnet": 21}
    assert {p["seat"] for p in positions} <= set(SEATS)
    for p in positions:
        assert p["position_id"] == f"{p['episode_id']}:t{p['tick']}"
        assert 1 <= p["tick"] <= 36
    digests = [p[view] for p in positions for view in ("situation", "full_record")]
    assert len(set(digests)) == 128


def test_panel_system_blocks_rebuild_from_the_public_bank():
    bank = {sc.scenario_id: sc for sc in load_bank("v1")}
    for p in PANEL["positions"]:
        sc = bank[p["scenario_id"]]
        assert sc.params.D == 36
        assert sha(forecast_system_block(sc)) == p["system_sha256"], p["position_id"]


def _synthetic_campaign(tmp_path: Path, ticks=(8, 20, 31)):
    """A v1-trio-shaped directory: one scripted episode and a selection."""
    sc = load_bank("v1")[5]
    trajectories = tmp_path / "campaign" / "trajectories"
    agents = {s: ModelAgent(ModelSpec(slug="scripted/model"), ScriptedModelClient(sc))
              for s in SEATS}
    run_episode(sc, agents, trajectories, bank="v1", episode_id="synthetic-00")
    log = trajectories / "synthetic-00.jsonl"
    records = read_jsonl(log)
    events = load_events(records)
    rows, positions = [], []
    system = forecast_system_block(sc).decode("utf-8")
    for tick in ticks:
        views = build_decision_views(sc, events, records, predicted_tick=tick,
                                     shuffle_salt=PANEL["shuffle_salt"])
        seat = fold_mod.state_at(sc, events, tick).mover
        rows.append({"episode_id": "synthetic-00", "tick": tick, "seat": seat,
                     "scenario_id": sc.scenario_id, "log_sha256": sha(log.read_bytes()),
                     # archived Windows path from another checkout: only the name is used
                     "log": "C:\\elsewhere\\trajectories\\synthetic-00.jsonl"})
        positions.append({
            "position_id": f"synthetic-00:t{tick}", "trajectory_sha256": sha(log.read_bytes()),
            "system_sha256": sha(system.encode("utf-8")),
            **{name: canonical_sha([{"role": "system", "content": system},
                                    {"role": "user", "content": views.rendered[view]}])
               for name, view in PANEL["views"].items()},
        })
    (tmp_path / "campaign" / "selection.json").write_text(
        json.dumps({"natural": rows}), "utf-8")
    manifest = {"cells": [{"position_id": p["position_id"], "view": name,
                           "prompt_sha256": p[name]}
                          for p in positions for name in PANEL["views"]
                          for _forecaster in range(2)]}
    return tmp_path / "campaign", {"positions": positions}, manifest


def test_panel_check_runs_on_a_synthetic_campaign(tmp_path, verify):
    source, golden, manifest = _synthetic_campaign(tmp_path)
    tally, failures = Counter(), []
    verify.check_ordinary_panel(source, tally, failures, manifest, golden)
    assert failures == []
    assert tally["panel_situation_match"] == tally["panel_full_record_match"] == 3
    assert tally["panel_golden_vs_manifest_match"] == 6
    golden["positions"][1]["full_record"] = "0" * 64
    tally, failures = Counter(), []
    verify.check_ordinary_panel(source, tally, failures, None, golden)
    assert failures == ["panel synthetic-00:t20 full_record"]


# ------------------------------------------------------- objective golden
def test_objective_golden_shape():
    cells = OBJECTIVE["cells"]
    assert len(cells) == 384
    positions = Counter((c["episode_id"], c["tick"]) for c in cells)
    assert len(positions) == 64 and set(positions.values()) == {6}
    assert Counter(c["view"] for c in cells) == {"B0": 192, "B2_ordered": 192}
    assert tuple(OBJECTIVE["views"]) == ob.OBJECTIVE_VIEWS
    assert set(OBJECTIVE["trajectory_sha256"]) == {c["episode_id"] for c in cells}
    assert len(OBJECTIVE["trajectory_sha256"]) == 22
    for c in cells:
        _stage, eid, tick, predictor, view = c["cell_id"].split(":")
        assert (eid, tick, view) == (c["episode_id"], f"t{c['tick']}", c["view"])
        assert predictor in {"luna", "sonnet", "grok"}
        assert [letter for letter, _ in c["menu"]] == ["A", "B", "C"]
        assert sorted(pid for _, pid in c["menu"]) == sorted(PRIORITY_IDS)
    for (eid, tick) in positions:
        same = {c["state_sha256"] for c in cells if (c["episode_id"], c["tick"]) == (eid, tick)}
        assert len(same) == 1


def test_objective_wording_is_the_studys():
    text = "\n\n".join(ob.OBJECTIVE_MANDATE + "\n" + ob.objective_task(list(zip("ABC", order)))
                       for order in itertools.permutations(PRIORITY_IDS))
    assert sha(text) == OBJECTIVE_WORDING_SHA256


def test_objective_menu_is_a_keyed_permutation():
    seen = set()
    for i in range(40):
        key = f"forge-v2-00:t{i}:luna:B0"
        menu = ob.objective_menu("salt", key)
        assert menu == ob.objective_menu("salt", key)
        assert [letter for letter, _ in menu] == ["A", "B", "C"]
        assert sorted(pid for _, pid in menu) == sorted(PRIORITY_IDS)
        seen.add(tuple(pid for _, pid in menu))
    assert len(seen) == 6


def test_objective_prompt_reuses_the_forecast_evidence(tmp_path):
    sc = extend_scenario(load_bank("v1")[7])
    priorities = {"API": "P_SHIP", "DATA": "P_ALIGN", "QA": "P_GUARD"}
    agents = {s: ModelAgent(ModelSpec(slug="scripted/model"), ScriptedModelClient(sc),
                            mandate=f"priority:{p}") for s, p in priorities.items()}
    run_episode(sc, agents, tmp_path, bank="v1", episode_id="objective")
    records = read_jsonl(tmp_path / "objective.jsonl")
    views = build_decision_views(sc, load_events(records), records, predicted_tick=27,
                                 shuffle_salt="s", priorities=priorities)
    menu = ob.objective_menu("salt", "objective:t27:luna:B0")
    for view in ob.OBJECTIVE_VIEWS:
        forecast = render_view(views.blocks, view)
        objective = ob.render_objective_view(views.blocks, view, menu)
        assert forecast.removesuffix(PREDICTION_TASK + "\n") == \
            objective.removesuffix(ob.objective_task(menu) + "\n")
    system, forecast_system = ob.objective_system_block(sc), forecast_system_block(sc)
    head, _, rest = system.partition(b"## Mandate\n")
    fhead, _, frest = forecast_system.partition(b"## Mandate\n")
    assert head == fhead and rest.partition(b"\n\n")[2] == frest.partition(b"\n\n")[2]
    assert rest.partition(b"\n\n")[0] == ob.OBJECTIVE_MANDATE.encode("utf-8")
    assert b"- Turns: 72," in system


@pytest.mark.parametrize("reply, answer", [
    ("Reasoning.\nANSWER: B", "B"),
    ("ANSWER: A\nmore\n ANSWER: A ", "A"),
    ("ANSWER: A\nANSWER: C", None),
    ("the answer is B", None),
    ("ANSWER: D", None),
])
def test_objective_answer_parsing(reply, answer):
    letter, error = ob.parse_objective_answer(reply)
    assert letter == answer
    assert (error is None) == (answer is not None)
    if error:
        assert ob.objective_retry(error)["content"].startswith(f"That was rejected: {error}.")
