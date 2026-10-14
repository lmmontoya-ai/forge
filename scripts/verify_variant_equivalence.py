"""Prove the ported paper variants match the study repository's originals.

Runs the synthetic cases in `tests/paper_variant_cases.py` twice:

  harness  the study repository's own code (self_other_prediction
           forge_trio.priorities / views / forge_adapter, forge_sham,
           forge_clear_goal, and the campaign scripts' render patches),
           on top of an untouched export of the FORGE commit the paper
           ran (default tag paper-runs-84bc0fe, recorded in run logs as
           84bc0fe), in that repository's own Python;
  ported   this checkout's forge.variants and forge.reader.

and requires byte-identical system blocks, outbound message lists, logged
prompt digests, events, results, reader views, reader prompt digests,
leakage audits, replay prompts and priority assignments.  Zero cost: the
episodes use a scripted provider stand-in.

The study repository is only read: its modules are imported with bytecode
writing disabled and nothing is written inside it.

Usage:
  python scripts/verify_variant_equivalence.py --smoke-tests PATH [--write-golden]

`--write-golden` stores the harness output (compacted) as
tests/golden/paper_variants.json, which tests/test_variants.py checks
without needing the study repository.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "paper_variants.json"
FAMILIES = ("v1", "v2", "v3", "clear")
HARNESS_FILES = (
    "src/self_other_prediction/forge_trio/priorities.py",
    "src/self_other_prediction/forge_trio/views.py",
    "src/self_other_prediction/forge_trio/traces.py",
    "src/self_other_prediction/forge_trio/forge_adapter.py",
    "src/self_other_prediction/forge_sham.py",
    "src/self_other_prediction/forge_clear_goal.py",
    "scripts/forge_v2_campaign.py",
    "scripts/forge_v3_campaign.py",
    "scripts/forge_clear_goal_campaign.py",
)


# ------------------------------------------------------------ harness side
class HarnessBackend:
    """The study repository's original implementation, driven as it ran."""

    def __init__(self, family: str, pristine_src: Path):
        import forge_v2_campaign as V2
        from self_other_prediction.forge_trio import forge_adapter as A
        from self_other_prediction.forge_trio import priorities as P
        from self_other_prediction.forge_trio import views as VW

        V2.FORGE_SRC = pristine_src
        self.family, self.V2, self.A, self.P, self.VW = family, V2, A, P, VW
        self.ctx = None
        if family == "v2":
            V2.install_v2_patches()
            self.ctx = V2._CTX
        elif family == "v3":
            import forge_v3_campaign as V3
            V3.install_v3_patches()
            self.ctx = V3._CTX
        elif family == "clear":
            import forge_clear_goal_campaign as CG
            CG.install_render_patches()
            self.ctx = CG._CTX
        self._extension = V2.extension(V2.config())

    def extend(self, scenario):
        return self.P.extend_scenario(scenario, self._extension)

    def system_block(self, scenario, mandate: str) -> bytes:
        import forge.render.render as render_mod
        if self.family == "v2":
            self.ctx.priority_id = None
        return render_mod.system_block(scenario, mandate)

    def run_episode(self, scenario, mandates, episode_id, log_dir, client) -> None:
        from forge.runtime.agents import ModelAgent
        from forge.runtime.config import ModelSpec
        from forge.runtime.episode import run_episode

        if self.family == "v2":
            self.ctx.assignment = {s: m.split(":", 1)[1] for s, m in mandates.items()}
            self.ctx.version = "iter2"
            self.ctx.priority_id = None
        elif self.family == "v3":
            self.ctx.assignment = dict(mandates)
        elif self.family == "clear":
            self.ctx.assignments = dict(mandates)
        try:
            spec = ModelSpec(slug="scripted/model")
            agents = {seat: ModelAgent(spec, client, mandate=mandate)
                      for seat, mandate in mandates.items()}
            run_episode(scenario, agents, log_dir, bank="v1", episode_id=episode_id)
        finally:
            if self.family in ("v2", "v3"):
                self.ctx.assignment = None
            elif self.family == "clear":
                self.ctx.assignments = None

    def decision_views(self, scenario, events, records, tick, priorities) -> dict:
        from forge.core import fold as fold_mod
        from paper_variant_cases import AUDITED_VIEWS, SHUFFLE_SALT, sha

        if self.family == "v2":
            self.ctx.assignment = dict(priorities or {})
            self.ctx.priority_id = None
        try:
            views = self.A.build_decision_views(
                scenario, events, records, predicted_tick=tick, shuffle_salt=SHUFFLE_SALT)
            system = self.A.forecast_system_block(scenario)
            corpus = self.P.public_corpus(scenario)
        finally:
            if self.family == "v2":
                self.ctx.assignment = None
        state = fold_mod.state_at(scenario, events, tick)
        served = {name: text for name, text in views.rendered.items() if name in AUDITED_VIEWS}
        return {
            "forecast_system": sha(system),
            "views": {name: sha(text) for name, text in views.rendered.items()},
            "inputs": {name: self.VW.prompt_digest(system, text)
                       for name, text in views.rendered.items()},
            "state": views.state_sha256_before,
            "mover": state.mover,
            "trace_kinds": list(views.blocks.trace_kinds),
            "audit": self.P.audit_public_views(served, corpus=corpus, exempt=()),
        }

    def replay_prompts(self, scenario, events, tick, priorities) -> dict:
        # The four assembly lines of the study's collect_decision_cell
        # policy path, with the campaign's own system-block patch and
        # _extra_user_line.
        import forge.render.render as render_mod
        from forge.core import fold as fold_mod

        state = fold_mod.state_at(scenario, events, tick)
        seat = state.mover
        prefix = tuple(e for e in events if e.tick < tick)
        ids = self.P.PRIORITY_IDS
        wrong = {s: ids[(ids.index(p) + 1) % 3] for s, p in priorities.items() if s != seat}
        true = {s: p for s, p in priorities.items() if s != seat}
        out = {}
        for arm, partners in (("plain", None), ("partner_true", true),
                              ("partner_wrong", wrong)):
            self.ctx.assignment = dict(priorities)
            self.ctx.priority_id = priorities[seat]
            try:
                system_text = render_mod.system_block(scenario, "principal").decode("utf-8")
                user_text = render_mod.render_user(state, prefix, seat)
                cell = {"priority_id": priorities[seat], "seat": seat}
                if partners is not None:
                    cell["partner_priorities"] = partners
                extra = self.V2._extra_user_line(cell)
                if extra is not None:
                    user_text = user_text.rstrip() + "\n\n" + extra.rstrip() + "\n"
            finally:
                self.ctx.assignment = None
                self.ctx.priority_id = None
            out[arm] = self.VW.prompt_digest(system_text, user_text)
        return out

    def assign(self, episode_id: str, mode: str) -> dict:
        from paper_variant_cases import ASSIGN_SALT
        return self.P.assign_priorities(episode_id, salt=ASSIGN_SALT, mode=mode)


def run_side(args) -> None:
    workdir = Path(tempfile.mkdtemp(prefix=f"forge_{args.side}_{args.family}_"))
    if args.side == "harness":
        smoke = Path(args.smoke_tests).resolve()
        pristine_src = Path(args.pristine).resolve() / "src"
        sys.path.insert(0, str(pristine_src))
        import forge  # noqa: F401  (pins every forge import to the export)
        sys.path[1:1] = [str(ROOT / "tests"), str(smoke / "scripts"), str(smoke / "src"),
                         str(smoke / "ledger-experiments" / "harness")]
        if Path(forge.__file__).resolve().parents[1] != pristine_src:
            raise SystemExit(f"forge resolved to {forge.__file__}, not the export")
        backend = HarnessBackend(args.family, pristine_src)
    else:
        sys.path.insert(0, str(ROOT / "src"))
        sys.path.insert(1, str(ROOT / "tests"))
        from paper_variant_cases import PortedBackend
        backend = PortedBackend()
    from paper_variant_cases import compute_family
    try:
        output = compute_family(backend, args.family, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    Path(args.out).write_text(json.dumps(output, sort_keys=True, default=str), "utf-8")


# ------------------------------------------------------------- orchestration
def diff(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}: present on one side only")
            else:
                out.extend(diff(a[key], b[key], f"{path}/{key}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        out = []
        for index, (x, y) in enumerate(zip(a, b)):
            out.extend(diff(x, y, f"{path}[{index}]"))
        return out
    return [] if a == b else [f"{path}: {str(a)[:80]} != {str(b)[:80]}"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--smoke-tests", help="path to the study repository checkout")
    ap.add_argument("--forge-commit", default="paper-runs-84bc0fe",
                    help="the FORGE commit the study ran against")
    ap.add_argument("--harness-python", default=None,
                    help="interpreter for the study side (default: its .venv)")
    ap.add_argument("--families", nargs="*", default=list(FAMILIES))
    ap.add_argument("--write-golden", action="store_true")
    ap.add_argument("--side", choices=("harness", "ported"), help=argparse.SUPPRESS)
    ap.add_argument("--family", help=argparse.SUPPRESS)
    ap.add_argument("--pristine", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.side:
        run_side(args)
        return 0
    if not args.smoke_tests:
        ap.error("--smoke-tests is required")

    smoke = Path(args.smoke_tests).resolve()
    harness_python = args.harness_python or next(
        str(p) for p in (smoke / ".venv" / "Scripts" / "python.exe",
                         smoke / ".venv" / "bin" / "python") if p.exists())
    status_before = git(smoke, "status", "--porcelain")
    tmp = Path(tempfile.mkdtemp(prefix="forge_equivalence_"))
    try:
        return _compare(args, smoke, harness_python, status_before, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _compare(args, smoke: Path, harness_python: str, status_before: str, tmp: Path) -> int:
    pristine = tmp / f"forge_{args.forge_commit}"
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar",
                              args.forge_commit], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(pristine)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    this = str(Path(__file__).resolve())

    report, harness_outputs = {}, {}
    for family in args.families:
        sides = {}
        for side, python in (("harness", harness_python), ("ported", sys.executable)):
            out = tmp / f"{family}.{side}.json"
            cmd = [python, "-B", this, "--side", side, "--family", family, "--out", str(out)]
            if side == "harness":
                cmd += ["--smoke-tests", str(smoke), "--pristine", str(pristine)]
            proc = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True)
            if proc.returncode != 0:
                print(proc.stdout[-2000:], proc.stderr[-4000:], file=sys.stderr)
                raise SystemExit(f"{side} side failed for family {family}")
            sides[side] = json.loads(out.read_text("utf-8"))
        problems = diff(sides["harness"], sides["ported"])
        harness_outputs[family] = sides["harness"]
        report[family] = {
            "system_blocks": sum(len(v) for v in sides["ported"]["system_blocks"].values()),
            "episodes": len(sides["ported"]["episodes"]),
            "calls": sum(len(e["messages"]) for e in sides["ported"]["episodes"].values()),
            "view_positions": len(sides["ported"]["views"]),
            "replay_positions": len(sides["ported"]["replay"]),
            "differences": problems[:20],
            "difference_count": len(problems),
        }
    status_after = git(smoke, "status", "--porcelain")
    summary = {
        "forge_commit_harness_side": git(ROOT, "rev-parse", args.forge_commit + "^{commit}"),
        "forge_checkout_ported_side": git(ROOT, "rev-parse", "HEAD"),
        "smoke_tests_commit": git(smoke, "rev-parse", "HEAD"),
        "smoke_tests_harness_files_dirty": git(smoke, "status", "--porcelain", "--",
                                               *HARNESS_FILES) or "clean",
        "smoke_tests_status_unchanged": status_before == status_after,
        "families": report,
    }
    print(json.dumps(summary, indent=1))
    ok = all(r["difference_count"] == 0 for r in report.values()) and \
        summary["smoke_tests_status_unchanged"]
    if args.write_golden:
        if not ok or set(args.families) != set(FAMILIES):
            raise SystemExit("refusing to write the golden file: run every family "
                             "and resolve every difference first")
        sys.path.insert(0, str(ROOT / "tests"))
        from paper_variant_cases import compact
        golden = {
            "about": ("Synthetic-case outputs of the study repository's original FORGE "
                      "variant implementation; tests/test_variants.py requires this "
                      "checkout to reproduce them. Written by "
                      "scripts/verify_variant_equivalence.py --write-golden."),
            "forge_commit": summary["forge_commit_harness_side"],
            "smoke_tests_commit": summary["smoke_tests_commit"],
            "families": {family: compact(out) for family, out in harness_outputs.items()},
        }
        GOLDEN.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n", "utf-8",
                          newline="\n")
        print(f"wrote {GOLDEN.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
