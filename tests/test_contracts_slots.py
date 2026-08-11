"""Contract law (§5) and the Schelling subsystem (§7)."""
import pytest

from forge.core import actions as actions_mod
from forge.core import fold as fold_mod
from forge.core.events import Action
from forge.game import Game, IllegalAction
from forge.slots.extract import extract, matched_value, stake_awards


def _open_build(sc) -> Game:
    g = Game(sc)
    for seat in ("API", "DATA", "QA"):
        slots = {s.slot_id: s.menu[0] for s in sc.slots
                 if s.kind == "menu" and not s.addendum}
        g.play(Action("COMMIT", {"slots": slots}))
    return g


def test_contract_validation_total_at_proposal(sc):
    g = _open_build(sc)
    bad = [
        ({"parties": ["API"]}, "parties"),
        ({"parties": ["API", "DATA"],
          "binds": [{"slot_id": "M9", "value": "x"}]}, "slot"),
        ({"parties": ["API", "DATA"],
          "binds": [{"slot_id": "M2", "value": "nonsense"}]}, "menu"),
        ({"parties": ["API", "DATA"],
          "obliges": [{"seat": "QA", "task_id": "t3"}]}, "party"),
        ({"parties": ["API", "DATA"],
          "obliges": [{"seat": "DATA", "task_id": "t3", "by": 99}]}, "by"),
        ({"parties": ["API", "DATA"],
          "binds": [{"slot_id": "M1", "value": "cursor"},
                    {"slot_id": "M2", "value": "error"},
                    {"slot_id": "M3", "value": "iso8601"}]}, "caps"),
        ({"parties": ["API", "DATA"],
          "binds": [{"slot_id": "M4", "value": "csv"}]}, "addendum slot"),
    ]
    for contract, label in bad:
        with pytest.raises(IllegalAction):
            g.play(Action("PROPOSE_IFACE", {"contract": contract}))


def test_lock_lapse_and_latest_lock_wins(sc):
    g = _open_build(sc)
    g.play(Action("PROPOSE_IFACE", {"contract": {
        "parties": ["API", "DATA"],
        "binds": [{"slot_id": "M2", "value": sc.slot("M2").menu[0]}]}}))
    g.play(Action("AGREE", {"contract_id": 1}))
    assert g.state.contracts[1].locked
    assert g.state.current_binding("M2")[2] == sc.slot("M2").menu[0]
    g.play(Action("WAIT", {}))  # QA
    g.play(Action("PROPOSE_IFACE", {"contract": {   # API re-binds M2
        "parties": ["API", "DATA"],
        "binds": [{"slot_id": "M2", "value": sc.slot("M2").menu[3]}]}}))
    g.play(Action("AGREE", {"contract_id": 2}))
    assert g.state.current_binding("M2")[2] == sc.slot("M2").menu[3]
    # a proposer cannot agree to its own offer; a stranger cannot agree
    g.play(Action("WAIT", {}))  # QA
    g.play(Action("PROPOSE_IFACE", {"contract": {
        "parties": ["API", "QA"],
        "binds": [{"slot_id": "M1", "value": sc.slot("M1").menu[1]}]}}))
    with pytest.raises(IllegalAction):
        g.play(Action("AGREE", {"contract_id": 3}))       # DATA not a party
    g.play(Action("WAIT", {}))
    # lapse: C3 opened at tick 10, lapses at 16 unagreed
    c = g.state.contracts[3]
    assert c.lapse_tick == c.tick_opened + 6
    while g.state.tick < c.lapse_tick:
        g.play(Action("WAIT", {}))
    with pytest.raises(IllegalAction):
        g.play(Action("AGREE", {"contract_id": 3}))


def test_breach_flags_pure(sc):
    from forge.render.breach import breaches
    g = _open_build(sc)
    v0, v1 = sc.slot("M2").menu[0], sc.slot("M2").menu[1]
    g.play(Action("PROPOSE_IFACE", {"contract": {
        "parties": ["API", "DATA"],
        "binds": [{"slot_id": "M2", "value": v0}]}}))
    g.play(Action("AGREE", {"contract_id": 1}))
    assert breaches(g.state) == []
    g.play(Action("WAIT", {}))
    # API writes api.py with a contradicting M2 literal: machine-detectable
    content = g.state.workspace["api.py"].replace(f'ERR_KEY = "{v0}"',
                                                  f'ERR_KEY = "{v1}"')
    g.play(Action("WRITE", {"path": "api.py", "content": content}))
    flags = breaches(g.state)
    assert any(b["kind"] == "slot" and b["slot"] == "M2" for b in flags)


def test_matching_symmetric_and_stakes_settle_together(sc):
    slot = sc.slot("M2")
    ws = {p: f'{slot.const_name} = "{slot.menu[2]}"\n' for p in slot.artifacts}
    assert matched_value(ws, slot) == slot.menu[2]
    awards = stake_awards(ws, sc, False)
    for seat, pref in slot.prefs.items():
        assert (awards[seat] >= 1) == (pref == slot.menu[2])


def test_extractor_bottom_on_placeholder(sc):
    slot = sc.slot("M1")
    assert extract({"api.py": 'PAGE_TOKEN = "TBD"\n'}, slot, "api.py") is None
    assert extract({}, slot, "api.py") is None
    assert extract({"api.py": "nothing here\n"}, slot, "api.py") is None


def test_flow_slot_canonicalization(sc):
    slot = sc.slot("F1")
    ws = {"api.py": 'ID_FIELD = "Rec_ID"\n', "data.py": 'ID_FIELD = "rec_id"\n'}
    assert matched_value(ws, slot) == "rec_id"
