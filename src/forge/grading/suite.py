"""Deterministic test evaluation, cached by workspace hash (§13).

Check specs are engine data, one of a small closed vocabulary; hidden and
public tests share the evaluator.  Hidden addendum tests are unpassable
before the amendment (§3.1).
"""
from __future__ import annotations

import hashlib
import json

from ..core.scenario import Scenario
from ..slots.extract import matched_value
from .sandbox import call, load_workspace

_cache: dict = {}


def workspace_hash(files: dict) -> str:
    payload = json.dumps(sorted(files.items())).encode()
    return hashlib.sha256(payload).hexdigest()


def _eq(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)


def eval_check(sc: Scenario, files: dict, modules: dict, check: dict) -> bool:
    kind = check["kind"]
    if kind == "match_slot":
        return matched_value(files, sc.slot(check["slot"])) is not None
    if kind == "const":
        ns = modules.get(check["file"][:-3])
        if ns is None or isinstance(ns, Exception):
            return False
        return ns.get(check["name"]) == check["expect"]
    if kind == "defines":
        ns = modules.get(check["file"][:-3])
        if ns is None or isinstance(ns, Exception):
            return False
        return callable(ns.get(check["name"]))
    if kind in ("call", "call_key", "call_ok"):
        ok, value = call(modules, check["file"][:-3], check["fn"],
                         check.get("args", []))
        if not ok:
            return False
        if kind == "call_ok":
            return value is not None
        if kind == "call_key":
            return isinstance(value, dict) and \
                _eq(value.get(check["key"]), check["expect"])
        return _eq(value, check["expect"])
    raise ValueError(f"unknown check kind {kind!r}")


def run_all(sc: Scenario, files: dict, amended: bool) -> dict:
    """{'public': {pid: bool}, 'hidden': {hid: bool}} — pure, cached."""
    key = (sc.scenario_id, workspace_hash(files), amended)
    if key in _cache:
        return _cache[key]
    modules = load_workspace(files)
    public = {p.test_id: eval_check(sc, files, modules, p.check)
              for p in sc.public}
    hidden = {}
    for h in sc.hidden:
        if h.addendum and not amended:
            hidden[h.test_id] = False
        else:
            hidden[h.test_id] = eval_check(sc, files, modules, h.check)
    result = {"public": public, "hidden": hidden}
    _cache[key] = result
    return result


def public_results(sc: Scenario, files: dict) -> dict:
    return run_all(sc, files, True)["public"]


def hidden_results(sc: Scenario, files: dict, amended: bool) -> dict:
    return run_all(sc, files, amended)["hidden"]


def hidden_score(sc: Scenario, files: dict, amended: bool) -> int:
    res = hidden_results(sc, files, amended)
    return sum(h.weight for h in sc.hidden if res[h.test_id])


def fragment_bonus_weight(sc: Scenario, files: dict, amended: bool,
                          seat: str) -> int:
    """B_s: summed weight of passed hidden tests whose R(h) names the seat."""
    res = hidden_results(sc, files, amended)
    return sum(h.weight for h in sc.hidden
               if res[h.test_id] and seat in h.req)
