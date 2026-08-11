"""ledger -> state.  Pure fold (design §3.3).

`apply(state, event)` assumes the action was validated (or is an
engine-flagged invalid WAIT).  fold(step(L,a)) == apply(fold(L), a) is a
property test.  Engine consequences are functions of the tick, never
separate events: the amendment materializes at the end of tick tau_amend,
offers lapse at the end of their lapse tick, contracts lock the instant the
last named party agrees.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .events import Action, Event, SEATS, mover_at
from .scenario import Scenario, ENGINE_ARTIFACTS
from .text import truncate_tokens

HOME_ARTIFACT = {"API": "api.py", "DATA": "data.py", "QA": "qa_expectations.py"}
BOTTOM = "TBD"     # the unset slot literal placeholder (⊥)


@dataclass(frozen=True)
class Contract:
    cid: int
    proposer: str
    parties: tuple                # 2 or 3 seat names, proposer included
    binds: tuple                  # ((slot_id, value), ...) at most 2
    obliges: tuple                # ({seat, task_id, by}|by=None as dict), at most 2
    tick_opened: int
    lapse_tick: int
    agreed_by: tuple = ()         # non-proposer parties that have AGREEd
    locked: bool = False
    lock_tick: int | None = None

    def is_offer_live(self, tick: int) -> bool:
        return not self.locked and tick <= self.lapse_tick


@dataclass(frozen=True)
class Release:
    rid: int
    tick: int
    seat: str
    snapshot: dict                # path -> content at release


@dataclass(frozen=True)
class State:
    scenario: Scenario
    tick: int                     # last applied tick; 0 before any action
    workspace: dict               # path -> content
    runs_left: int
    probes_left: int
    tokens_left: int
    commitments: dict             # seat -> {slot_id: value} (menu slots)
    contracts: dict               # cid -> Contract
    releases: tuple               # of Release
    open_files: dict              # seat -> tuple of paths (LRU, cap 2)
    last_run: tuple | None        # (tick, seat)
    probes: tuple = ()            # (tick, test_id)  results computed purely
    n_contracts: int = 0

    @property
    def over(self) -> bool:
        return self.tick >= self.scenario.params.D

    @property
    def mover(self) -> str:
        return mover_at(self.tick + 1)

    @property
    def amended(self) -> bool:
        return self.tick >= self.scenario.params.tau_amend

    @property
    def phase0(self) -> bool:
        return self.tick < self.scenario.params.phase0_end and not self.over

    def graded_workspace(self) -> dict:
        """The release state (§8.1): last release, else current workspace."""
        if self.releases:
            return self.releases[-1].snapshot
        return self.workspace

    def committed(self, seat: str) -> bool:
        return seat in self.commitments

    def current_binding(self, slot_id: str):
        """Latest-lock-wins (§5): the newest locked contract binding the slot."""
        best = None
        for c in self.contracts.values():
            if c.locked:
                for sid, value in c.binds:
                    if sid == slot_id:
                        if best is None or c.lock_tick > best[0]:
                            best = (c.lock_tick, c.cid, value)
        return best            # (lock_tick, cid, value) or None

    def current_obligations(self):
        """task_id -> (lock_tick, cid, seat, by), latest lock wins per task."""
        out = {}
        for c in self.contracts.values():
            if c.locked:
                for ob in c.obliges:
                    t = out.get(ob["task_id"])
                    if t is None or c.lock_tick > t[0]:
                        out[ob["task_id"]] = (c.lock_tick, c.cid,
                                              ob["seat"], ob.get("by"))
        return out


def initial_state(sc: Scenario) -> State:
    ws = {p: c for p, c in sc.skeletons.items() if p != "SPEC_ADDENDUM.md"}
    return State(
        scenario=sc, tick=0, workspace=ws,
        runs_left=sc.params.run_budget, probes_left=sc.params.probe_budget,
        tokens_left=sc.params.release_tokens,
        commitments={}, contracts={}, releases=(),
        open_files={s: () for s in SEATS}, last_run=None,
    )


def set_slot_literal(content: str, const_name: str, value: str) -> str:
    """Anchored substitution: rewrite the `NAME = "..."` line (§7.1: the value
    appears as a literal in a declared position, scaffolded in the skeletons)."""
    out = []
    done = False
    for line in content.split("\n"):
        if not done and line.startswith(f"{const_name} = "):
            out.append(f'{const_name} = "{value}"')
            done = True
        else:
            out.append(line)
    return "\n".join(out)


def _apply_commit(state: State, seat: str, slots: dict) -> State:
    """Registers commitments and pre-wires the seat's home artifact so the
    committed values are its initial slot literals (§7.3)."""
    home = HOME_ARTIFACT[seat]
    content = state.workspace[home]
    sc = state.scenario
    committed = {}
    for slot_id, value in slots.items():
        slot = sc.slot(slot_id)
        committed[slot_id] = value
        if home in slot.artifacts:
            content = set_slot_literal(content, slot.const_name, value)
    ws = dict(state.workspace)
    ws[home] = content
    return replace(state,
                   commitments={**state.commitments, seat: committed},
                   workspace=ws)


def apply(state: State, ev: Event) -> State:
    sc = state.scenario
    p = sc.params
    a, seat = ev.action, ev.seat
    name, args = a.name, a.args
    st = state

    if name == "COMMIT":
        st = _apply_commit(st, seat, dict(args.get("slots", {})))
    elif name == "READ":
        path = args["path"]
        reg = [q for q in st.open_files[seat] if q != path] + [path]
        reg = reg[-p.open_files_cap:]
        st = replace(st, open_files={**st.open_files, seat: tuple(reg)})
    elif name == "WRITE":
        ws = dict(st.workspace)
        ws[args["path"]] = args["content"]
        st = replace(st, workspace=ws)
    elif name == "RUN":
        st = replace(st, runs_left=st.runs_left - 1,
                     last_run=(ev.tick, seat))
    elif name == "PROBE":
        st = replace(st, probes_left=st.probes_left - 1,
                     probes=st.probes + ((ev.tick, args["test_id"]),))
    elif name == "RELEASE":
        rel = Release(rid=len(st.releases) + 1, tick=ev.tick, seat=seat,
                      snapshot=dict(st.workspace))
        st = replace(st, tokens_left=st.tokens_left - 1,
                     releases=st.releases + (rel,))
    elif name == "PROPOSE_IFACE":
        c = args["contract"]
        cid = st.n_contracts + 1
        lapse = ev.tick + min(p.contract_lapse, p.D - ev.tick)
        contract = Contract(
            cid=cid, proposer=seat,
            parties=tuple(c["parties"]),
            binds=tuple((b["slot_id"], b["value"]) for b in c.get("binds", [])),
            obliges=tuple(dict(o) for o in c.get("obliges", [])),
            tick_opened=ev.tick, lapse_tick=lapse)
        st = replace(st, contracts={**st.contracts, cid: contract},
                     n_contracts=cid)
    elif name == "AGREE":
        cid = int(args["contract_id"])
        c = st.contracts[cid]
        agreed = c.agreed_by + (seat,)
        others = [q for q in c.parties if q != c.proposer]
        locked = all(q in agreed for q in others)
        c2 = replace(c, agreed_by=agreed, locked=locked,
                     lock_tick=ev.tick if locked else None)
        st = replace(st, contracts={**st.contracts, cid: c2})
    # REPORT, QUERY, INFORM, WAIT, REFUSE change no folded state; they live
    # in the ledger and are rendered from it.

    return replace(st, tick=ev.tick)


def fold(sc: Scenario, events) -> State:
    st = initial_state(sc)
    for ev in events:
        st = apply(st, ev)
    return st


def state_at(sc: Scenario, events, tick: int) -> State:
    """The state a mover saw at `tick`: all events strictly before it applied."""
    st = initial_state(sc)
    for ev in events:
        if ev.tick >= tick:
            break
        st = apply(st, ev)
    return st


def truncate_message(action: Action, cap: int) -> tuple[Action, bool]:
    """Engine-boundary message truncation, recorded (§4)."""
    if action.name in ("QUERY", "INFORM", "REFUSE") and action.args.get("text"):
        cut, was = truncate_tokens(action.args["text"], cap)
        if was:
            return Action(action.name, {**action.args, "text": cut}), True
    return action, False
