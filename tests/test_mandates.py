"""Mandate variants (Phase-0 objective test): only the Mandate paragraph
varies, the default cannot drift from system.txt, unknown variants refuse."""
import pytest

from forge.render.render import mandate_variants, system_block


def test_principal_verbatim_matches_system_txt(sc):
    base = system_block(sc)
    text = mandate_variants()["principal"]["text"].encode()
    assert text in base, "the frozen default drifted from system.txt"


def test_only_mandate_paragraph_varies(sc):
    base = system_block(sc)
    for name in ("own", "joint"):
        variant = system_block(sc, name)
        v = mandate_variants()
        assert v[name]["text"].encode() in variant
        stripped_a = base.replace(v["principal"]["text"].encode(), b"@")
        stripped_b = variant.replace(v[name]["text"].encode(), b"@")
        assert stripped_a == stripped_b, name


def test_unknown_variant_refused(sc):
    with pytest.raises(KeyError):
        system_block(sc, "maximize-chaos")


def test_own_and_joint_keep_ledger_sentence_structure():
    v = mandate_variants()
    assert "highest final score you can for yourself" in v["own"]["text"]
    assert "their concern, not yours" in v["own"]["text"]
    assert "combined final score" in v["joint"]["text"]
    assert "matters less than its total" in v["joint"]["text"]
    for name in ("own", "joint"):
        assert v[name]["text"].endswith("Use your judgment.")