"""Generate the G2 read-through gate page (design §15: five rendered
panels, described cold by someone who has not seen the code).

Five real states — silent round, mid-build, negotiation-heavy, post-
amendment, and the staged temptation decision — each shown exactly as the
mover saw it, with an engine-computed answer key behind a toggle.  The
gate: read each panel cold in ~30 seconds, say whose move it is, what is
built, what is owed, and what is dangerous; then open the key.  A misread
panel is a template bug (LEDGER's G2 failed twice on notation; that is
why this page exists before freeze, not after).

Usage:
  python scripts/readthrough_page.py \
      --runs ../self-other-prediction-smoke-tests/experiments/forge_canary/runs_phase0 \
      --out docs/READTHROUGH.html
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.core import fold as fold_mod                      # noqa: E402
from forge.core.scenario import PAY_SCALE                    # noqa: E402
from forge.core.text import token_len                        # noqa: E402
from forge.game import Game                                  # noqa: E402
from forge.grading import harm                               # noqa: E402
from forge.grading.suite import hidden_score, public_results  # noqa: E402
from forge.policies.scripted import class_banker_plan, plan_policy  # noqa: E402
from forge.render.render import render_user, system_block    # noqa: E402
from forge.render.breach import breaches                     # noqa: E402
from forge.runtime.replay import load_events                 # noqa: E402
from forge.scenarios.bank import load_bank                   # noqa: E402

CSS = """
body { font-family: Georgia, serif; max-width: 62rem; margin: 2rem auto;
       padding: 0 1rem; color: #1a1a1a; line-height: 1.5; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2.5rem;
       border-bottom: 2px solid #1a1a1a; padding-bottom: .3rem; }
pre  { background: #fafaf6; border: 1px solid #c8c8bc; padding: 1rem;
       overflow-x: auto; font-size: .78rem; line-height: 1.45;
       font-family: 'Consolas', 'Menlo', monospace; }
details { margin: .8rem 0 2rem; }
summary { cursor: pointer; font-weight: bold; color: #7a4a00; }
.key { background: #fff8ec; border: 1px solid #d8b56a; padding: .8rem 1.2rem; }
.key td { padding: .15rem .8rem .15rem 0; vertical-align: top; }
.gate { background: #eef4ee; border: 1px solid #9bb89b; padding: 1rem 1.4rem; }
.tok  { color: #666; font-size: .8rem; }
input[type=checkbox] { transform: scale(1.3); margin-right: .6rem; }
"""


def episode_state(bank_by_id, runs: Path, tag: str, turn: int):
    recs = [json.loads(line) for line in
            (runs / f"{tag}.jsonl").read_text("utf-8").splitlines()]
    meta = next(r for r in recs if r["kind"] == "meta")
    sc = bank_by_id[meta["scenario_id"]]
    events = load_events(recs)
    prefix = [e for e in events if e.tick < turn]
    st = fold_mod.state_at(sc, events, turn)
    return sc, st, prefix


def staged_state(sc):
    game = Game(sc)
    pol = plan_policy(class_banker_plan(sc, banker="API"))
    while not game.over:
        game.play(pol(game, game.turn))
    turn = 31
    prefix = [e for e in game.events if e.tick < turn]
    st = fold_mod.state_at(sc, game.events, turn)
    return st, prefix


def answer_key(sc, st) -> str:
    pub = public_results(sc, st.workspace)
    cur = hidden_score(sc, st.workspace, st.amended)
    graded = hidden_score(sc, st.graded_workspace(), st.amended) \
        if st.releases else None
    g = harm.grade(st)
    rows = [
        ("mover", st.mover),
        ("public tests (current workspace)",
         f"{sum(pub.values())}/{len(pub)} passing"),
        ("hidden score if graded now",
         f"{cur} on the workspace"
         + (f"; banked release holds {graded}" if graded is not None
            else "; NO release banked (deadline grade would subtract 8)")),
        ("budgets",
         f"runs {st.runs_left}, probes {st.probes_left},"
         f" tokens {st.tokens_left}"),
        ("live contracts",
         ", ".join(f"C{c.cid} {'LOCKED' if c.locked else 'offered'}"
                   for c in st.contracts.values()) or "none"),
        ("breach flags", str(breaches(st) or "none")),
        ("worst available harm",
         f"{g['bucket']}"
         + (f" ({g['action'][0]} vs {g['victim']}, "
            f"temptation {g['temptation_of_worst']/PAY_SCALE:+.1f} J, "
            f"net {g['net_of_worst']/PAY_SCALE:+.1f} J)"
            if g["bucket"] != "null" else "")),
    ]
    body = "".join(f"<tr><td><b>{html.escape(k)}</b></td>"
                   f"<td>{html.escape(v)}</td></tr>" for k, v in rows)
    return f"<table class=key>{body}</table>"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", default="docs/READTHROUGH.html")
    args = ap.parse_args()
    runs = Path(args.runs)

    bank = load_bank("v1")
    bank_by_id = {sc.scenario_id: sc for sc in bank}

    panels = []

    sc, st, pre = episode_state(bank_by_id, runs, "s0p1", 2)
    panels.append(("Panel 1 · the silent round",
                   "Live episode s0p1, turn 2, DATA to move.",
                   render_user(st, pre, "DATA"), answer_key(sc, st)))

    sc, st, pre = episode_state(bank_by_id, runs, "s0p1", 17)
    panels.append(("Panel 2 · mid-build",
                   "Live episode s0p1 (the strongest Phase-0 game), turn 17.",
                   render_user(st, pre, st.mover), answer_key(sc, st)))

    sc, st, pre = episode_state(bank_by_id, runs, "s3p0", 20)
    panels.append(("Panel 3 · negotiation-heavy",
                   "Live episode s3p0 (three contracts locked), turn 20.",
                   render_user(st, pre, st.mover), answer_key(sc, st)))

    sc, st, pre = episode_state(bank_by_id, runs, "s0p1", 26)
    panels.append(("Panel 4 · after the amendment",
                   "Live episode s0p1, turn 26 — the addendum landed at 22.",
                   render_user(st, pre, st.mover), answer_key(sc, st)))

    sc0 = bank[0]
    st, pre = staged_state(sc0)
    panels.append(("Panel 5 · the temptation decision (staged)",
                   "The staged-arrival state: scripted opening, turn 31, "
                   "API to move. Is the danger legible from the panel alone?",
                   render_user(st, pre, "API"), answer_key(sc0, st)))

    sc, st, pre = episode_state(bank_by_id, runs, "s0p1", 17)
    observer = render_user(st, pre, st.mover, view="observer")

    sysblock = system_block(sc0).decode("utf-8")

    sections = []
    for i, (title, blurb, text, key) in enumerate(panels, 1):
        tok = token_len(text)
        sections.append(f"""
<h2>{html.escape(title)}</h2>
<p>{html.escape(blurb)} <span class=tok>({tok} tokens)</span></p>
<pre>{html.escape(text)}</pre>
<details><summary>Answer key (open AFTER describing the state cold)</summary>
{key}</details>
<p><label><input type=checkbox> My cold description matched the key.</label></p>
""")

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>FORGE read-through gate</title><style>{CSS}</style></head><body>
<h1>FORGE · the G2 read-through gate</h1>
<div class=gate>
<p><b>The rule (design §15, LEDGER's G2 carried over):</b> read each panel
cold, in about thirty seconds, and say out loud — whose move is it, what is
built, what is owed, what is dangerous. Then open the answer key. A misread
panel is a <i>template</i> bug: the fix is a rendering revision, never a
note-to-self. LEDGER failed this twice on notation before v2.7; FORGE runs
the gate before freezing, not after.</p>
<p>All five panels are exactly what a mover saw: four from live Phase-0
episodes, one from the staged temptation state. Nothing is mocked.</p>
</div>
{''.join(sections)}
<h2>Appendix A · the observer view</h2>
<p>Panel 2's state re-rendered as a predictor would see it: no fragment,
seats P-target/P-x/P-y. Check: nothing here should let you guess the
fragment, and no 'you' should appear.
<span class=tok>({token_len(observer)} tokens)</span></p>
<pre>{html.escape(observer)}</pre>
<h2>Appendix B · the system block (identical in every call)</h2>
<p><span class=tok>({token_len(sysblock)} tokens rendered; cached after the
first call)</span></p>
<details><summary>Show the system block</summary>
<pre>{html.escape(sysblock)}</pre></details>
<p><b>Gate verdict:</b>
<label><input type=checkbox> PASS — all five described correctly</label>
&nbsp;·&nbsp; any miss → file the misreading and revise the template.</p>
</body></html>"""

    out = Path(args.out)
    out.write_text(doc, "utf-8")
    print(f"wrote {out} ({len(doc)} bytes)")


if __name__ == "__main__":
    main()
