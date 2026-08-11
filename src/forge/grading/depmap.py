"""The dependency map (§9.3, §9.5): which tests depend on which file.

Static: a test depends on the file its check names, plus every workspace
module that file transitively imports.  Matching tests depend on every
artifact expressing the slot.
"""
from __future__ import annotations

import re

from ..core.scenario import Scenario


def imports_of(files: dict) -> dict:
    names = {p[:-3] for p in files if p.endswith(".py")}
    out = {}
    for p, content in files.items():
        if not p.endswith(".py"):
            continue
        found = set()
        for m in re.finditer(r"^\s*(?:import|from)\s+([a-z_][a-z0-9_]*)",
                             content, re.MULTILINE):
            if m.group(1) in names:
                found.add(m.group(1) + ".py")
        out[p] = found
    return out


def transitive_deps(files: dict, path: str) -> set:
    imp = imports_of(files)
    seen, todo = set(), [path]
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        todo.extend(imp.get(p, ()))
    return seen


def check_files(sc: Scenario, check: dict) -> set:
    if check["kind"] == "match_slot":
        return set(sc.slot(check["slot"]).artifacts)
    return {check["file"]}


def tests_depending_on(sc: Scenario, files: dict, path: str) -> dict:
    """{'public': [...], 'hidden': [...]} test ids whose outcome can depend
    on `path` (directly or through imports)."""
    public, hidden = [], []
    for p in sc.public:
        if any(path in transitive_deps(files, f)
               for f in check_files(sc, p.check)):
            public.append(p.test_id)
    for h in sc.hidden:
        if any(path in transitive_deps(files, f)
               for f in check_files(sc, h.check)):
            hidden.append(h.test_id)
    return {"public": public, "hidden": hidden}


def task_public_tests(sc: Scenario, task_id: str) -> list:
    return [p.test_id for p in sc.public if p.task_id == task_id]


def task_covered_by(sc: Scenario, files: dict, path: str, task_id: str) -> bool:
    """Whether `path` is in the dependency set of the task's public tests."""
    tids = task_public_tests(sc, task_id)
    if not tids:
        return False
    dep = tests_depending_on(sc, files, path)["public"]
    return any(t in dep for t in tids)
