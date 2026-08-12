"""Render: golden bytes, digests, observer leakage, token bounds."""
import hashlib
from pathlib import Path

import pytest

from forge.core import fold as fold_mod
from forge.core.text import _encoder, token_len
from forge.render.render import render_prompt, render_user, system_block

GOLDEN = Path(__file__).parent / "golden"


def _t17_view(sc, coop_game, viewer="DATA", view="mover"):
    events = [e for e in coop_game.events if e.tick < 17]
    st = fold_mod.state_at(sc, coop_game.events, 17)
    return st, events, render_user(st, events, viewer, view=view)


def test_golden_panel_t17(sc, coop_game):
    _, _, text = _t17_view(sc, coop_game)
    digest = hashlib.sha256(text.encode()).hexdigest()
    want = (GOLDEN / "t17_data.sha256").read_text().strip()
    assert digest == want, "render bytes changed; re-freeze deliberately"


def test_render_pure_same_bytes(sc, coop_game):
    st, events, first = _t17_view(sc, coop_game)
    for _ in range(3):
        assert render_user(st, events, "DATA") == first
    d1 = render_prompt(st, events, "DATA")[1]
    d2 = render_prompt(st, events, "DATA")[1]
    assert d1 == d2


def test_system_block_byte_identical(sc):
    assert system_block(sc) == system_block(sc)
    assert b"## Mandate" in system_block(sc)
    assert sc.spec_md.encode() in system_block(sc)


def test_observer_view_leaks_nothing(sc, coop_game):
    st, events, text = _t17_view(sc, coop_game, viewer="DATA",
                                 view="observer")
    # no fragment bytes from any seat
    for seat, frag in sc.fragments.items():
        assert frag[:40] not in text
    assert "## Your fragment" not in text
    assert "you " not in text.lower().replace("your move", "")
    assert "P-target" in text
    # observer header names the mover abstractly
    assert "observer view · P-target to move" in text


def test_observer_open_files_are_targets(sc, coop_game):
    events = [e for e in coop_game.events if e.tick < 17]
    st = fold_mod.state_at(sc, coop_game.events, 17)
    text = render_user(st, events, st.mover, view="observer")
    reg = st.open_files.get(st.mover, ())
    for path in reg:
        assert f"## Open file: {path}" in text


def test_message_text_hidden_from_third_seat(sc, coop_game):
    events = [e for e in coop_game.events if e.tick < 17]
    st = fold_mod.state_at(sc, coop_game.events, 17)
    qa_view = render_user(st, events, "QA")
    assert "constants are in" not in qa_view       # API->DATA at t7
    data_view = render_user(st, events, "DATA")
    assert "constants are in" in data_view


needs_tiktoken = pytest.mark.skipif(_encoder() is None,
                                    reason="tiktoken unavailable")


@needs_tiktoken
@pytest.mark.token_bounds
def test_token_bounds(sc, coop_game):
    from forge.render.panel import render_panel
    from forge.render.history import render_history
    events = [e for e in coop_game.events if e.tick < 17]
    st = fold_mod.state_at(sc, coop_game.events, 17)
    panel = render_panel(st, events, "DATA")
    assert token_len(panel) <= 340
    for seat, frag in sc.fragments.items():
        assert token_len(frag + "\n" + sc.fragment_addenda[seat]) <= 120
    # per-class history bounds (finding F-B, docs/SPEC_FINDINGS.md: the
    # design's flat 10-token non-message bound cannot hold for contract
    # lines, exactly as LEDGER's uniform-8 claim failed its tokenizer)
    hist = render_history(st, events, "DATA")
    for line in hist.split("\n")[1:]:
        if "PROPOSE_IFACE" in line:
            cap = 44
        elif "REPORT" in line:
            cap = 32
        elif '"' in line:
            cap = 56
        elif "[" in line:
            cap = 24            # simple line with a consequence bracket
        else:
            cap = 16
        assert token_len(line) <= cap, line
    for path, content in st.workspace.items():
        if path.endswith(".py"):
            assert token_len(content) <= 640, path
