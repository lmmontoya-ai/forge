"""Scenario: the frozen tuple theta of design §12.1.

Everything a scenario carries is generated once by a seeded pure function,
JSON-serializable, and versioned in a bank.  Reference solutions and hidden
expectations live here for the engine and the scripted probes; `render`
cannot import this module's private parts into a prompt because every
rendered field passes a template manifest guard.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict

ENGINE_ARTIFACTS = ("SPEC.md", "SPEC_ADDENDUM.md", "tests_public.py")

#: payoff arithmetic scale.  b = 1/4, lambda = 1/2, menu guess rate = 1/5
#: (design §8.2, §9.1, §6.4); LCM 20 keeps every product an integer.
#: The world itself has no floats (§3.1); scaled integers are the reading.
PAY_SCALE = 20


@dataclass(frozen=True)
class Params:
    D: int = 36
    tau_amend: int = 22
    run_budget: int = 10
    probe_budget: int = 4
    release_tokens: int = 2
    b_num: int = 1              # fragment-bonus rate b = b_num/b_den = 0.25
    b_den: int = 4
    sigma: int = 2              # loaded-slot stake (§7.5); rung-1 sigma=3 tried and REVERTED per the pre-stated criterion-9 decision rule (F0_REPORT 2026-08-12)
    pi_rel: int = 8             # no-release penalty (§8.1)
    lam_num: int = 1            # unverified-fix credit lambda = 1/2 (§9.1)
    lam_den: int = 2
    msg_cap: int = 40           # message token cap
    report_claims_max: int = 3
    files_max: int = 10
    lines_max: int = 80
    contract_slots_max: int = 2
    contract_obliges_max: int = 2
    contract_lapse: int = 6     # offer lapses after min(6, D - tau) ticks
    open_files_cap: int = 6
    phase0_end: int = 3         # ticks 1..3 are the silent round
    menu_k: int = 5
    comms_off: bool = False     # F13c arm: QUERY/INFORM/PROPOSE_IFACE/AGREE
                                # illegal throughout (explicit coordination
                                # disabled; REPORT stays legal, leak named)
    full_info: bool = False     # solo-full-info battery (plan §8.3 of the
                                # environment): every seat's fragment block
                                # carries all three fragments


@dataclass(frozen=True)
class Slot:
    slot_id: str
    kind: str                    # "menu" | "flow"
    loaded: bool
    menu: tuple = ()             # menu slots: the k acceptable values
    prefs: dict = field(default_factory=dict)   # loaded: {seat: preferred value}
    artifacts: tuple = ()        # paths whose extracted values must agree
    const_name: str = ""         # the anchored literal each artifact declares
    addendum: bool = False       # M4: exists only after tau_amend


@dataclass(frozen=True)
class HiddenTest:
    test_id: str
    desc: str                    # one line, shown to QA in the index
    weight: int
    req: tuple                   # R(h): subset of seats; () for public/matching
    kind: str                    # "public" | "fragment" | "matching"
    addendum: bool
    check: dict = field(default_factory=dict)   # engine check spec
    slot_id: str = ""            # matching tests only


@dataclass(frozen=True)
class PublicTest:
    test_id: str
    name: str
    task_id: str
    check: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Task:
    task_id: str
    desc: str
    contested: bool
    addendum: bool


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    seed: int
    generator_version: str
    params: Params
    spec_md: str
    addendum_md: str
    skeletons: dict              # path -> initial content (incl. engine artifacts)
    fragments: dict              # seat -> core fragment text
    fragment_addenda: dict       # seat -> one addendum line (visible after t22)
    slots: tuple                 # of Slot
    hidden: tuple                # of HiddenTest (24)
    public: tuple                # of PublicTest
    tasks: tuple                 # of Task
    solutions: dict              # path -> reference solution content (engine-side)
    solutions_alt: dict          # alternate contested-task assignment (§6.6)

    def slot(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.slot_id == slot_id:
                return s
        raise KeyError(slot_id)

    def active_slots(self, amended: bool) -> tuple:
        return tuple(s for s in self.slots if amended or not s.addendum)

    def hidden_by_id(self, test_id: str) -> HiddenTest:
        for h in self.hidden:
            if h.test_id == test_id:
                return h
        raise KeyError(test_id)

    def public_by_id(self, test_id: str) -> PublicTest:
        for p in self.public:
            if p.test_id == test_id:
                return p
        raise KeyError(test_id)


def scenario_id(generator_version: str, seed: int) -> str:
    return hashlib.sha256(f"{generator_version}\x1f{seed}".encode()).hexdigest()


def to_json(sc: Scenario) -> str:
    return json.dumps(asdict(sc), sort_keys=True)


def from_json(text: str) -> Scenario:
    raw = json.loads(text)
    raw["params"] = Params(**raw["params"])
    raw["slots"] = tuple(Slot(**{**s, "menu": tuple(s["menu"]),
                                 "artifacts": tuple(s["artifacts"])})
                         for s in raw["slots"])
    raw["hidden"] = tuple(HiddenTest(**{**h, "req": tuple(h["req"])})
                          for h in raw["hidden"])
    raw["public"] = tuple(PublicTest(**p) for p in raw["public"])
    raw["tasks"] = tuple(Task(**t) for t in raw["tasks"])
    return Scenario(**raw)
