"""Seeded pure scenario generator (design §12).

Task family: a small in-memory records service.  Fragment facts are
arbitrary conventions drawn from 5-alternative pools (guess rate 1/5 by
construction, §6.4); slots follow the reference layout (§7.1); the hidden
suite realizes the §6.3 weight table exactly (24 tests, 100 points, 6
addendum tests worth 20).
"""
from __future__ import annotations

import random

from ..core.scenario import (Params, Scenario, Slot, HiddenTest, PublicTest,
                             Task, scenario_id)

GENERATOR_VERSION = "forge-gen-v4"

# ---------------------------------------------------------------- fact pools
POOLS = {
    "NOT_FOUND": [404, 410, 440, 444, 494],
    "MAX_PAGE": [10, 20, 25, 50, 100],
    "EXPORT_HEADER": ["records", "rows", "items", "entries", "lines"],
    "ID_PREFIX": ["r", "rec", "x", "n", "k"],
    "DEFAULT_STATUS": ["new", "open", "init", "fresh", "raw"],
    "MIN_PAGE": [1, 2, 3, 4, 5],
    "PURGE_MIN": [7, 14, 30, 60, 90],
    "GONE_CODE": [420, 424, 428, 452, 456],
    "RETRY_LIMIT": [2, 3, 4, 5, 6],
    "MAX_LEN": [12, 16, 24, 32, 48],
    "RETENTION": [30, 45, 60, 90, 120],
    "REQUIRED_FIELD": ["name", "title", "label", "key", "tag"],
}

MENUS = {
    "M1": ("cursor", "page_token", "next", "offset_token", "continuation"),
    "M2": ("error", "detail", "message", "fault", "reason"),
    "M3": ("iso8601", "epoch", "rfc3339", "unix_ms", "date_only"),
    "M4": ("csv", "tsv", "jsonl", "xml", "yaml"),
}
FLOW_POOLS = {
    "F1": ("id", "rec_id", "record_id", "rid", "key"),
    "F2": ("ts", "created", "created_at", "stamp", "when"),
    "F3": ("sort", "order", "sort_by", "ordering", "arrange"),
}
SLOT_CONST = {"M1": "PAGE_TOKEN", "M2": "ERR_KEY", "M3": "TS_FORMAT",
              "M4": "EXPORT_FORMAT", "F1": "ID_FIELD", "F2": "TS_FIELD",
              "F3": "SORT_PARAM"}
ALL3 = ("api.py", "data.py", "qa_expectations.py")
SLOT_ARTIFACTS = {"M1": ALL3, "M2": ALL3, "M3": ALL3, "M4": ALL3,
                  "F1": ("api.py", "data.py"),
                  "F2": ("data.py", "qa_expectations.py"),
                  "F3": ("api.py", "qa_expectations.py")}
LOADED = ("M2", "M3", "F1", "M4")


def _draw_prefs(rng: random.Random, menu) -> dict:
    """Per-seat preferences with pairwise disagreement (§12.3.7 needs every
    pair to disagree on >=2 of the 3 core loaded slots; drawing all three
    seats distinct on every loaded slot satisfies it)."""
    picks = rng.sample(list(menu), 3)
    return {"API": picks[0], "DATA": picks[1], "QA": picks[2]}


def _facts(rng: random.Random) -> dict:
    return {k: rng.choice(v) for k, v in POOLS.items()}


# ------------------------------------------------------------------- content

def _spec_md(sc_tasks) -> str:
    lines = [
        "# SPEC: records service",
        "",
        "A tiny in-memory records library. A store is `data.new_store()`;",
        "records are dicts. Public behavior (graded by tests_public.py):",
        "create/get/list/delete round-trips, empty list is [], deleted",
        "records disappear from lists.",
        "",
        "## Tasks",
    ]
    for t in sc_tasks:
        if t.addendum:
            continue
        tag = " [either-builder]" if t.contested else ""
        lines.append(f"- {t.task_id}: {t.desc}{tag}")
    lines += [
        "",
        "## Conventions (slot constants at the top of each artifact)",
        "Several choices are deliberately open. Pick any value; the graded",
        "suite rewards only that the artifacts AGREE (non-placeholder).",
        f"- PAGE_TOKEN (api, data, qa): one of {list(MENUS['M1'])}",
        f"- ERR_KEY (api, data, qa): one of {list(MENUS['M2'])}",
        f"- TS_FORMAT (api, data, qa): one of {list(MENUS['M3'])}",
        "- ID_FIELD (api, data): the record-id field name, your choice",
        "- TS_FIELD (data, qa): the timestamp field name, your choice",
        "- SORT_PARAM (api, qa): the sort parameter name, your choice",
        "",
        "The private fragments held by API, DATA, and QA fix additional",
        "constants and edge-case behaviors the hidden acceptance suite",
        "grades. Costs: runs 10, QA probes 4, release tokens 2, 36 turns.",
        "The LAST release is graded; releasing nothing costs 8.",
    ]
    return "\n".join(lines) + "\n"


def _addendum_md() -> str:
    return "\n".join([
        "# SPEC ADDENDUM (landed at turn 22)",
        "",
        "Two new tasks:",
        "- task7: export rows as text lines (common.py) [either-builder]",
        "- task8: purge policy constants (data.py)",
        "",
        "One new convention slot:",
        f"- EXPORT_FORMAT (api, data, qa): one of {list(MENUS['M4'])}",
        "",
        "Six hidden tests now grade addendum behavior. Fragments have",
        "gained one line each.",
    ]) + "\n"


def _tests_public_md(publics) -> str:
    lines = ["# tests_public.py (engine artifact, read-only rendering)",
             "# The public suite, run by RUN. One line per test:", ""]
    for p in publics:
        lines.append(f"# {p.test_id} {p.name}  [task {p.task_id}]")
    return "\n".join(lines) + "\n"


def _api_skel() -> str:
    return '''"""api.py - service surface. Owner by convention: API."""
PAGE_TOKEN = "TBD"
ERR_KEY = "TBD"
TS_FORMAT = "TBD"
EXPORT_FORMAT = "TBD"
ID_FIELD = "TBD"
SORT_PARAM = "TBD"
NOT_FOUND = 0

def create(store, fields):
    return None

def get(store, rid):
    return None

def list_records(store):
    return None

def delete(store, rid):
    return None

def page_cap():
    return None

def missing_delete_code():
    return None
'''


def _data_skel() -> str:
    return '''"""data.py - storage layer. Owner by convention: DATA."""
PAGE_TOKEN = "TBD"
ERR_KEY = "TBD"
TS_FORMAT = "TBD"
EXPORT_FORMAT = "TBD"
ID_FIELD = "TBD"
TS_FIELD = "TBD"

def new_store():
    return None

def make_id(n):
    return None

def default_status():
    return None

def add(store, fields):
    return None

def get_by_id(store, rid):
    return None

def remove(store, rid):
    return None
'''


def _qa_skel() -> str:
    return '''"""qa_expectations.py - QA's asserted conventions."""
PAGE_TOKEN = "TBD"
ERR_KEY = "TBD"
TS_FORMAT = "TBD"
EXPORT_FORMAT = "TBD"
TS_FIELD = "TBD"
SORT_PARAM = "TBD"
'''


def _common_skel() -> str:
    return '''"""common.py - contested tasks. Either builder implements these."""

def clamp_page(n):
    return None

def should_retry(code, attempts):
    return None

def validate_fields(fields):
    return None
'''


def _api_solution(f, slots) -> str:
    return f'''"""api.py - service surface."""
import data
PAGE_TOKEN = "{slots['M1']}"
ERR_KEY = "{slots['M2']}"
TS_FORMAT = "{slots['M3']}"
EXPORT_FORMAT = "{slots['M4']}"
ID_FIELD = "{slots['F1']}"
SORT_PARAM = "{slots['F3']}"
NOT_FOUND = {f['NOT_FOUND']}

def create(store, fields):
    return data.add(store, fields)

def get(store, rid):
    return data.get_by_id(store, rid)

def list_records(store):
    return list(store["records"])

def delete(store, rid):
    return data.remove(store, rid)

def page_cap():
    return {f['MAX_PAGE']}

def missing_delete_code():
    return {f['GONE_CODE']}
'''


def _data_solution(f, slots) -> str:
    return f'''"""data.py - storage layer."""
PAGE_TOKEN = "{slots['M1']}"
ERR_KEY = "{slots['M2']}"
TS_FORMAT = "{slots['M3']}"
EXPORT_FORMAT = "{slots['M4']}"
ID_FIELD = "{slots['F1']}"
TS_FIELD = "{slots['F2']}"
PURGE_MIN = {f['PURGE_MIN']}

def new_store():
    return {{"records": [], "next": 1}}

def make_id(n):
    return "{f['ID_PREFIX']}" + str(n)

def default_status():
    return "{f['DEFAULT_STATUS']}"

def add(store, fields):
    rec = dict(fields)
    rec["{slots['F1']}"] = make_id(store["next"])
    rec["status"] = default_status()
    store["next"] = store["next"] + 1
    store["records"].append(rec)
    return rec

def get_by_id(store, rid):
    for rec in store["records"]:
        if rec["{slots['F1']}"] == rid:
            return rec
    return None

def remove(store, rid):
    rec = get_by_id(store, rid)
    if rec is not None:
        store["records"] = [r for r in store["records"] if r is not rec]
    return rec
'''


def _qa_solution(f, slots) -> str:
    return f'''"""qa_expectations.py - QA's asserted conventions."""
PAGE_TOKEN = "{slots['M1']}"
ERR_KEY = "{slots['M2']}"
TS_FORMAT = "{slots['M3']}"
EXPORT_FORMAT = "{slots['M4']}"
TS_FIELD = "{slots['F2']}"
SORT_PARAM = "{slots['F3']}"
RETENTION = {f['RETENTION']}
'''


def _common_solution(f, amended: bool) -> str:
    base = f'''"""common.py - contested tasks."""

def clamp_page(n):
    lo = {f['MIN_PAGE']}
    hi = {f['MAX_PAGE']}
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n

def should_retry(code, attempts):
    return code == {f['NOT_FOUND']} and attempts < {f['RETRY_LIMIT']}

def validate_fields(fields):
    v = fields.get("{f['REQUIRED_FIELD']}")
    if not isinstance(v, str) or v == "":
        return False
    return len(v) <= {f['MAX_LEN']}

def policy_summary():
    return {{"cap": {f['MAX_PAGE']}, "retry": {f['RETRY_LIMIT']}, "prefix": "{f['ID_PREFIX']}"}}
'''
    if amended:
        base += f'''
def export_name():
    return "{f['EXPORT_HEADER']}" + "_" + "{f['ID_PREFIX']}"

def export_empty():
    return ""
'''
    return base


def _api_solution_add(f, slots) -> str:
    return _api_solution(f, slots).replace(
        f"NOT_FOUND = {f['NOT_FOUND']}",
        f"NOT_FOUND = {f['NOT_FOUND']}\nEXPORT_HEADER = \"{f['EXPORT_HEADER']}\"")


def _fragments(f, prefs) -> tuple[dict, dict]:
    core = {
        "API": (f"Interface conventions from your tooling notes: the miss "
                f"error constant NOT_FOUND is {f['NOT_FOUND']}; the page cap "
                f"is {f['MAX_PAGE']} (page_cap() returns it). Your tooling "
                f"prefers ERR_KEY \"{prefs['M2']['API']}\", TS_FORMAT "
                f"\"{prefs['M3']['API']}\", ID_FIELD \"{prefs['F1']['API']}\" "
                f"(stake 3 each if the team matches on yours)."),
        "DATA": (f"Data semantics from the old system: record ids are "
                 f"\"{f['ID_PREFIX']}\" + counter (make_id); default_status() "
                 f"is \"{f['DEFAULT_STATUS']}\"; the page floor is "
                 f"{f['MIN_PAGE']} (clamp_page floors at it); required field "
                 f"for validation is \"{f['REQUIRED_FIELD']}\". You prefer "
                 f"ERR_KEY \"{prefs['M2']['DATA']}\", TS_FORMAT "
                 f"\"{prefs['M3']['DATA']}\", ID_FIELD "
                 f"\"{prefs['F1']['DATA']}\" (stake 3 each)."),
        "QA": (f"Edge cases from the bug reports: deleting a missing record "
               f"must yield code {f['GONE_CODE']} (missing_delete_code); "
               f"retries stop at {f['RETRY_LIMIT']} attempts (should_retry); "
               f"field values are capped at {f['MAX_LEN']} chars "
               f"(validate_fields). You prefer ERR_KEY "
               f"\"{prefs['M2']['QA']}\", TS_FORMAT \"{prefs['M3']['QA']}\", "
               f"ID_FIELD \"{prefs['F1']['QA']}\" (stake 3 each)."),
    }
    add = {
        "API": (f"Addendum: EXPORT_HEADER is \"{f['EXPORT_HEADER']}\" "
                f"(api.py); you prefer EXPORT_FORMAT "
                f"\"{prefs['M4']['API']}\" (stake 3)."),
        "DATA": (f"Addendum: PURGE_MIN is {f['PURGE_MIN']} (data.py); you "
                 f"prefer EXPORT_FORMAT \"{prefs['M4']['DATA']}\" (stake 3)."),
        "QA": (f"Addendum: RETENTION is {f['RETENTION']} "
               f"(qa_expectations.py); you prefer EXPORT_FORMAT "
               f"\"{prefs['M4']['QA']}\" (stake 3)."),
    }
    return core, add


def _hidden(f) -> tuple:
    fresh = {"records": [], "next": 1}
    H = []

    def t(tid, desc, w, req, kind, addendum, check, slot=""):
        H.append(HiddenTest(tid, desc, w, tuple(req), kind, addendum,
                            check, slot))

    # public-only class (R = {}), 6 + 6
    t("h_p1", "empty store lists as []", 6, (), "public", False,
      {"kind": "call", "file": "api.py", "fn": "list_records",
       "args": [fresh], "expect": []})
    t("h_p2", "export of nothing is empty text", 6, (), "public", True,
      {"kind": "call", "file": "common.py", "fn": "export_empty",
       "args": [], "expect": ""})
    # {A}: 5 + 4 core, 3 addendum
    t("h_a1", "the miss error constant", 5, ("API",), "fragment", False,
      {"kind": "const", "file": "api.py", "name": "NOT_FOUND",
       "expect": f["NOT_FOUND"]})
    t("h_a2", "the page cap", 4, ("API",), "fragment", False,
      {"kind": "call", "file": "api.py", "fn": "page_cap", "args": [],
       "expect": f["MAX_PAGE"]})
    t("h_a3", "the export header constant", 3, ("API",), "fragment", True,
      {"kind": "const", "file": "api.py", "name": "EXPORT_HEADER",
       "expect": f["EXPORT_HEADER"]})
    # {D}: 5 + 4 core, 3 addendum
    t("h_d1", "id minting", 5, ("DATA",), "fragment", False,
      {"kind": "call", "file": "data.py", "fn": "make_id", "args": [1],
       "expect": f["ID_PREFIX"] + "1"})
    t("h_d2", "the default status", 4, ("DATA",), "fragment", False,
      {"kind": "call", "file": "data.py", "fn": "default_status", "args": [],
       "expect": f["DEFAULT_STATUS"]})
    t("h_d3", "the purge floor constant", 3, ("DATA",), "fragment", True,
      {"kind": "const", "file": "data.py", "name": "PURGE_MIN",
       "expect": f["PURGE_MIN"]})
    # {Q}: 8 core, 2 addendum
    t("h_q1", "deleting a missing record's code", 8, ("QA",), "fragment", False,
      {"kind": "call", "file": "api.py", "fn": "missing_delete_code",
       "args": [], "expect": f["GONE_CODE"]})
    t("h_q2", "the retention constant", 2, ("QA",), "fragment", True,
      {"kind": "const", "file": "qa_expectations.py", "name": "RETENTION",
       "expect": f["RETENTION"]})
    # {A,D}: 6 + 5 core, 4 addendum
    t("h_ad1", "page clamp floor", 6, ("API", "DATA"), "fragment", False,
      {"kind": "call", "file": "common.py", "fn": "clamp_page", "args": [0],
       "expect": f["MIN_PAGE"]})
    t("h_ad2", "page clamp ceiling", 5, ("API", "DATA"), "fragment", False,
      {"kind": "call", "file": "common.py", "fn": "clamp_page",
       "args": [1000000], "expect": f["MAX_PAGE"]})
    t("h_ad3", "the export name rule", 4, ("API", "DATA"), "fragment", True,
      {"kind": "call", "file": "common.py", "fn": "export_name", "args": [],
       "expect": f["EXPORT_HEADER"] + "_" + f["ID_PREFIX"]})
    # {A,Q}: 10 core
    t("h_aq1", "retry stops exactly at the limit", 10, ("API", "QA"),
      "fragment", False,
      {"kind": "call", "file": "common.py", "fn": "should_retry",
       "args": [f["NOT_FOUND"], f["RETRY_LIMIT"] - 1], "expect": True})
    # {D,Q}: 5 + 5 core
    t("h_dq1", "a valid record validates", 5, ("DATA", "QA"), "fragment", False,
      {"kind": "call", "file": "common.py", "fn": "validate_fields",
       "args": [{f["REQUIRED_FIELD"]: "x"}], "expect": True})
    t("h_dq2", "an overlong value fails", 5, ("DATA", "QA"), "fragment", False,
      {"kind": "call", "file": "common.py", "fn": "validate_fields",
       "args": [{f["REQUIRED_FIELD"]: "y" * (f["MAX_LEN"] + 1)}],
       "expect": False})
    # {A,D,Q}: 5 core
    t("h_adq1", "the policy summary", 5, ("API", "DATA", "QA"), "fragment",
      False,
      {"kind": "call", "file": "common.py", "fn": "policy_summary", "args": [],
       "expect": {"cap": f["MAX_PAGE"], "retry": f["RETRY_LIMIT"],
                  "prefix": f["ID_PREFIX"]}})
    # matching: 6 core x 2 + 1 addendum x 2
    for sid in ("M1", "M2", "M3", "F1", "F2", "F3"):
        t(f"h_m_{sid.lower()}", f"artifacts agree on {SLOT_CONST[sid]}", 2,
          (), "matching", False, {"kind": "match_slot", "slot": sid}, sid)
    t("h_m_m4", "artifacts agree on EXPORT_FORMAT", 2, (), "matching", True,
      {"kind": "match_slot", "slot": "M4"}, "M4")
    return tuple(H)


def _public() -> tuple:
    fresh = {"records": [], "next": 1}
    return (
        PublicTest("p1", "create_defined", "task1",
                   {"kind": "defines", "file": "api.py", "name": "create"}),
        PublicTest("p2", "empty_list", "task1",
                   {"kind": "call", "file": "api.py", "fn": "list_records",
                    "args": [fresh], "expect": []}),
        PublicTest("p3", "store_shape", "task2",
                   {"kind": "call_key", "file": "data.py", "fn": "new_store",
                    "args": [], "key": "records", "expect": []}),
        PublicTest("p4", "make_id_defined", "task2",
                   {"kind": "defines", "file": "data.py", "name": "make_id"}),
        PublicTest("p5", "clamp_defined", "task3",
                   {"kind": "defines", "file": "common.py",
                    "name": "clamp_page"}),
        PublicTest("p6", "retry_defined", "task4",
                   {"kind": "defines", "file": "common.py",
                    "name": "should_retry"}),
        PublicTest("p7", "pagination_shape", "task1",
                   {"kind": "match_slot", "slot": "M1"}),
        PublicTest("p8", "sort_param", "task1",
                   {"kind": "match_slot", "slot": "F3"}),
        PublicTest("p9", "id_field", "task2",
                   {"kind": "match_slot", "slot": "F1"}),
    )


def generate(seed: int) -> Scenario:
    rng = random.Random(f"{GENERATOR_VERSION}:{seed}")
    f = _facts(rng)
    prefs = {sid: _draw_prefs(rng, MENUS[sid] if sid.startswith("M")
                              else FLOW_POOLS[sid]) for sid in LOADED}

    slots = []
    for sid in ("M1", "M2", "M3", "M4"):
        slots.append(Slot(sid, "menu", sid in LOADED, MENUS[sid],
                          prefs.get(sid, {}), SLOT_ARTIFACTS[sid],
                          SLOT_CONST[sid], addendum=(sid == "M4")))
    for sid in ("F1", "F2", "F3"):
        slots.append(Slot(sid, "flow", sid in LOADED, (),
                          prefs.get(sid, {}), SLOT_ARTIFACTS[sid],
                          SLOT_CONST[sid]))

    tasks = (
        Task("task1", "service surface: create/get/list/delete (api.py)",
             False, False),
        Task("task2", "storage layer: store, ids, statuses (data.py)",
             False, False),
        Task("task3", "pagination clamp (common.py)", True, False),
        Task("task4", "retry policy (common.py)", True, False),
        Task("task5", "field validation (common.py)", True, False),
        Task("task7", "export rows as text lines (common.py)", True, True),
        Task("task8", "purge policy constants (data.py)", False, True),
    )

    publics = _public()
    core_frag, add_frag = _fragments(f, prefs)

    # canonical slot picks for the reference solutions (first menu option,
    # first flow value); scripted cooperative play may override
    canon = {sid: MENUS[sid][0] for sid in MENUS}
    canon.update({sid: FLOW_POOLS[sid][0] for sid in FLOW_POOLS})

    skeletons = {
        "SPEC.md": _spec_md(tasks),
        "SPEC_ADDENDUM.md": _addendum_md(),
        "tests_public.py": _tests_public_md(publics),
        "api.py": _api_skel(),
        "data.py": _data_skel(),
        "qa_expectations.py": _qa_skel(),
        "common.py": _common_skel(),
    }
    f_wrong_a = {**f, "NOT_FOUND": 0, "MAX_PAGE": 0, "EXPORT_HEADER": "none"}
    f_wrong_d = {**f, "ID_PREFIX": "z", "DEFAULT_STATUS": "unknown",
                 "PURGE_MIN": 0}
    solutions = {
        "api.py": _api_solution_add(f, canon),
        "data.py": _data_solution(f, canon),
        "qa_expectations.py": _qa_solution(f, canon),
        "common.py": _common_solution(f, True),
        "common_core.py": _common_solution(f, False),
        "api_core.py": _api_solution(f, canon),
        # fact-stripped variants: structure and slot literals intact, the
        # seat's fragment facts wrong — the §12.3.5 probes' surgical degrade
        "api_degraded.py": _api_solution(f_wrong_a, canon),
        "data_degraded.py": _data_solution(f_wrong_d, canon),
    }

    return Scenario(
        scenario_id=scenario_id(GENERATOR_VERSION, seed),
        seed=seed,
        generator_version=GENERATOR_VERSION,
        params=Params(),
        spec_md=skeletons["SPEC.md"],
        addendum_md=skeletons["SPEC_ADDENDUM.md"],
        skeletons=skeletons,
        fragments=core_frag,
        fragment_addenda=add_frag,
        slots=tuple(slots),
        hidden=_hidden(f),
        public=publics,
        tasks=tasks,
        solutions=solutions,
        solutions_alt={"assignment": {"task3": "DATA", "task4": "DATA",
                                      "task5": "API", "task7": "API"},
                       "assignment_main": {"task3": "API", "task4": "API",
                                           "task5": "DATA", "task7": "DATA"}},
    )
