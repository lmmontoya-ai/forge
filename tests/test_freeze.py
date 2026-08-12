"""The freeze defends itself: every artifact the Phase-0 manifest hashed
must still hash the same.  Changing any of them is legitimate ONLY with a
deliberate re-freeze (rerun scripts/freeze_manifest.py and say why)."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "FREEZE_MANIFEST.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_frozen_artifacts_unchanged():
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    for rel, want in manifest["artifacts"].items():
        got = _sha(ROOT / rel)
        assert got == want, (
            f"{rel} changed since the Phase-0 freeze; if deliberate, "
            f"re-run scripts/freeze_manifest.py and record why")


def test_manifest_names_the_flag():
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    assert "temptation" in manifest["premia"]
    assert "never the flag" in manifest["premia"]["net"]
    assert manifest["confirmatory_mandate"] == "principal"