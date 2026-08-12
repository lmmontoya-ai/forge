"""History renderer (design §10.3): one line per past tick, fixed grammar
(spec/templates.v1/history.grammar.txt).  WRITE lines carry path and line
count, never content; message text renders only where the viewer was a
party (in the observer view: where the TARGET was a party, since the
observer sees the target's information state minus the fragment).
"""
from __future__ import annotations

from ..core import fold as fold_mod
from ..grading.suite import hidden_results, public_results
from .breach import breaches
from .panel import seat_namer


def render_history(state, events, viewer: str, *, view: str = "mover") -> str:
    sc = state.scenario
    rel = seat_namer(state, viewer, view)
    subject = viewer if view == "mover" else state.mover  # whose info state
    # the header row exists because the seat names are domain nouns: a cold
    # reader parsed "turn 1  API  COMMIT" without registering API as the
    # actor (read-through gate finding G2-1).  LEDGER never needed this —
    # its actors were you/them, unmistakably people.
    lines = ["## History", "TURN WHO       DID"]
    st = fold_mod.initial_state(sc)
    prev_breach_keys: set = set()
    for ev in events:
        before = st
        st = fold_mod.apply(st, ev)
        name, args = ev.action.name, ev.action.args
        rest = ""
        notes = []
        if name == "COMMIT":
            rest = "slots committed"
        elif name == "READ":
            rest = args["path"]
        elif name == "WRITE":
            n = len(args["content"].split("\n"))
            rest = f"{args['path']} ({n} lines)"
        elif name == "RUN":
            res = public_results(sc, st.workspace)
            notes.append(f"{sum(res.values())}/{len(res)} passing")
        elif name == "PROBE":
            rest = args["test_id"]
            if ev.seat == subject or subject == "QA":
                ok = hidden_results(sc, st.workspace,
                                    st.amended)[args["test_id"]]
                notes.append("pass" if ok else "fail")
        elif name == "RELEASE":
            notes.append(f"r{len(st.releases)} is the graded candidate")
        elif name == "PROPOSE_IFACE":
            c = st.contracts[st.n_contracts]
            binds = " · ".join(f"{sid}={v}" for sid, v in c.binds)
            obl = " · ".join(
                f"{rel(o['seat'])}: {o['task_id']}"
                + (f" by turn {o['by']}" if o.get("by") else "")
                for o in c.obliges)
            parts = "+".join(rel(q) for q in c.parties)
            body = " · ".join(x for x in (binds, obl) if x)
            rest = f"C{c.cid}: {body} ({parts})"
        elif name == "AGREE":
            cid = int(args["contract_id"])
            rest = f"C{cid}"
            if st.contracts[cid].locked and not before.contracts[cid].locked:
                notes.append(f"C{cid} locked")
        elif name == "REPORT":
            rest = " · ".join(
                f"{c['scope'] if isinstance(c['scope'], str) else c['scope']['task_id']}"
                f"={c['verdict']}" for c in args["claims"])
        elif name in ("QUERY", "INFORM"):
            to = args["to"]
            if ev.seat == subject or to == subject:
                rest = f"-> {rel(to)} \"{args.get('text', '')}\""
            else:
                rest = f"msg -> {rel(to)}"
        elif name == "REFUSE":
            rest = f"\"{args.get('text', '')}\"" if args.get("text") else ""

        # engine consequences at this tick
        for cid, c in st.contracts.items():
            if not c.locked and c.lapse_tick == ev.tick:
                notes.append(f"C{cid} lapsed")
        new_flags = breaches(st)
        keys = {tuple(sorted(b.items(), key=lambda kv: kv[0]))
                if not isinstance(b, dict) else str(sorted(b.items()))
                for b in new_flags}
        for b in new_flags:
            k = str(sorted(b.items()))
            if k not in prev_breach_keys:
                what = b.get("slot") or b.get("task")
                notes.append(f"breach: C{b['cid']} {what}")
        prev_breach_keys = keys
        if ev.tick == sc.params.tau_amend:
            notes.append("amendment: SPEC_ADDENDUM.md landed")
        if ev.invalid:
            notes.append("invalid")
        if ev.truncated:
            notes.append("truncated")

        base = f"turn {ev.tick:<3} {rel(ev.seat):<9} {name} {rest}".rstrip()
        if notes:
            base += f"    [{'; '.join(notes)}]"
        lines.append(base)
    return "\n".join(lines)
