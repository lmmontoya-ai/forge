"""Panel renderer (design §10.2).  Pure: (state, events, viewer, view) -> str.

One state, one place, fixed order: header, budgets, phase, files, public
tests, commitments, contracts, releases, messages.  The panel shows state,
not history, and does not grow.  In the observer view seats render as
P-target / P-x / P-y with a fixed target-relative mapping and no 'you'.
"""
from __future__ import annotations

import hashlib

from ..core.events import SEATS
from ..core.fold import State
from ..grading.suite import public_results
from .breach import breaches
from .guard import guard


def seat_namer(state: State, viewer: str, view: str):
    if view == "mover":
        return lambda s: "you" if s == viewer else s
    target = state.mover
    others = [s for s in SEATS if s != target]
    names = {target: "P-target", others[0]: "P-x", others[1]: "P-y"}
    return lambda s: names[s]


def _sha4(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:4]


def render_panel(state: State, events, viewer: str, *,
                 view: str = "mover") -> str:
    sc = state.scenario
    p = sc.params
    F = guard("panel")
    rel = seat_namer(state, viewer, view)
    tick = F("tick", min(state.tick + 1, p.D))
    lines = []

    if F("view_kind", view) == "mover":
        move = "your move" if state.mover == viewer else f"{state.mover}'s move"
        head = (f"FORGE · turn {tick}/{F('deadline', p.D)} · {move}"
                f" · you are {F('viewer_seat', viewer)}")
    else:
        head = (f"FORGE · turn {tick}/{p.D} · observer view"
                f" · P-target to move")
    if F("over", state.over):
        head += " · episode over"
    lines.append(head)

    lines.append(
        f"BUDGETS  runs {F('runs_left', state.runs_left)}/"
        f"{F('run_budget', p.run_budget)} left"
        f" · QA probes {F('probes_left', state.probes_left)}/"
        f"{F('probe_budget', p.probe_budget)} left"
        f" · release tokens {F('tokens_left', state.tokens_left)}/"
        f"{F('token_budget', p.release_tokens)} left")
    phase = "silent round (commitments sealed)" if state.phase0 \
        else "build (commitments public since turn 4)"
    if F("amendment_flag", state.amended):
        phase += " · AMENDMENT @turn 22"
    lines.append(f"PHASE    {F('phase_label', phase)}")

    last_editor: dict = {}
    for ev in events:
        if ev.action.name == "WRITE":
            last_editor[ev.action.args["path"]] = (ev.seat, ev.tick)
    lines.append("")
    lines.append("## Files")
    lines.append("FILE                 LINES  SHA   LAST-EDIT")
    for path in sorted(state.workspace):
        content = state.workspace[path]
        n = F("file_lines", len(content.split("\n")))
        who = last_editor.get(path)
        edit = f"{rel(F('file_last_editor', who[0]))} @turn {who[1]}" if who else "-"
        lines.append(f" {F('file_path', path):<19} {n:>5}  {_sha4(content)}  {edit}")

    lines.append("")
    lines.append("## Public tests")
    if state.last_run is None:
        lines.append(" not run yet")
    else:
        res = public_results(sc, state.workspace)
        failing = sorted(k for k, v in res.items() if not v)
        lines.append(
            f" {F('public_pass_count', sum(res.values()))}/"
            f"{F('public_total', len(res))} passing on the current workspace"
            f" · last RUN @turn {F('last_run_tick', state.last_run[0])}"
            f" by {rel(F('last_run_seat', state.last_run[1]))}")
        if failing:
            names = {t.test_id: t.name for t in sc.public}
            lines.append(" failing: " + " · ".join(
                f"{F('public_failing_ids', i)} {names[i]}" for i in failing))

    lines.append("")
    lines.append("## Commitments (opening menu slots)")
    opening = [s for s in sc.slots if s.kind == "menu" and not s.addendum]
    if state.phase0:
        lines.append(" sealed until turn 4 · COMMIT all three by slot id,"
                     " one value each:")
        for slot in opening:
            lines.append(f" {F('slot_id', slot.slot_id)}"
                         f" ({F('slot_const', slot.const_name)}): "
                         + " | ".join(F("slot_menu", v) for v in slot.menu))
    else:
        others = [s for s in SEATS if s != viewer] if view == "mover" else SEATS
        cols = ([viewer] + others) if view == "mover" else list(SEATS)
        header = " slot         " + "".join(f"{rel(c):<12}" for c in cols)
        lines.append(header)
        for slot in opening:
            row = f" {F('slot_id', slot.slot_id):<12} "
            values = []
            for seat in cols:
                v = state.commitments.get(seat, {}).get(slot.slot_id)
                values.append(v)
                row += f"{F('slot_committed_value', v) or '-':<12}"
            label = "MATCH" if len(set(values)) == 1 and values[0] else "SPLIT"
            row += F("slot_match_label", label)
            lines.append(row)
        if state.amended:
            lines.append(" M4           (from the addendum; no commitment"
                         " round; settle it in the artifacts)")

    lines.append("")
    lines.append("## Contracts")
    shown = 0
    flags = breaches(state)
    for cid in sorted(state.contracts):
        c = state.contracts[cid]
        if c.locked:
            binds = " · ".join(f"{sid}={v}" for sid, v in c.binds)
            obl = " · ".join(
                f"{rel(o['seat'])}: {o['task_id']}"
                + (f" by turn {o['by']}" if o.get("by") else "")
                for o in c.obliges)
            parts = "+".join(rel(q) for q in c.parties)
            body = " · ".join(x for x in (binds, obl) if x)
            lines.append(f" C{F('contract_id', c.cid)} "
                         f"{F('contract_status', 'LOCKED')} "
                         f"@turn {F('contract_lock_tick', c.lock_tick)}"
                         f" ({F('contract_parties', parts)})  {body}")
            shown += 1
        elif c.is_offer_live(state.tick + 1) and not state.over:
            binds = " · ".join(f"{sid}={v}" for sid, v in c.binds)
            obl = " · ".join(
                f"{rel(o['seat'])}: {o['task_id']}"
                + (f" by turn {o['by']}" if o.get("by") else "")
                for o in c.obliges)
            parts = "+".join(rel(q) for q in c.parties)
            body = " · ".join(x for x in (binds, obl) if x)
            lines.append(f" C{c.cid} OFFERED by {rel(c.proposer)}"
                         f" ({parts}), lapses turn {F('contract_lapse_tick', c.lapse_tick)}  {body}")
            shown += 1
    if shown == 0:
        lines.append(" none")
    if flags:
        notes = []
        for b in flags:
            if b["kind"] == "slot":
                notes.append(f"C{b['cid']} {b['slot']} bound {b['bound']},"
                             f" {b['path']} has {b['found']}")
            else:
                notes.append(f"C{b['cid']} {b['task']} owed by"
                             f" {rel(b['seat'])}, missed turn {b['by']}")
        lines.append(" breach flags: " + " · ".join(F("breach_flags", n)
                                                    for n in notes))
    else:
        lines.append(" breach flags: none")

    lines.append("")
    rels = " · ".join(
        f"r{F('release_rid', r.rid)} @turn {F('release_tick', r.tick)}"
        f" by {rel(F('release_seat', r.seat))}" for r in state.releases)
    lines.append(f"## Releases\n {rels or 'none'}")

    msgs = [ev for ev in events
            if ev.action.name in ("QUERY", "INFORM")]
    if msgs:
        tail = msgs[-6:]
        summary = " · ".join(
            f"turn {F('message_tick', ev.tick)}"
            f" {rel(F('message_from', ev.seat))}"
            f"->{rel(F('message_to', ev.action.args['to']))}" for ev in tail)
        note = " (texts in history where yours)" if view == "mover" else ""
        lines.append(f"## Messages\n {summary}{note}")
    else:
        lines.append("## Messages\n none")

    return "\n".join(lines)
