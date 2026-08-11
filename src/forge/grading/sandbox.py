"""Embedded, sandboxed, deterministic execution of workspace modules (§13).

No clock, no filesystem, no network, no imports beyond workspace modules.
A trace-based step limiter bounds runaway code deterministically (Windows
has no SIGALRM, and wall-clock limits would not be deterministic anyway).
Results are pure in the workspace content.
"""
from __future__ import annotations

import re
import sys

STEP_LIMIT = 200_000

_SAFE_BUILTINS = {
    n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n)
    for n in (
        "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
        "frozenset", "getattr", "hasattr", "hash", "int", "isinstance",
        "issubclass", "iter", "len", "list", "map", "max", "min", "next",
        "range", "repr", "reversed", "round", "set", "setattr", "slice",
        "sorted", "str", "sum", "tuple", "zip",
        "ArithmeticError", "AssertionError", "AttributeError", "Exception",
        "IndexError", "KeyError", "LookupError", "NameError", "RuntimeError",
        "StopIteration", "TypeError", "ValueError", "ZeroDivisionError",
    )
}


class StepLimitExceeded(Exception):
    pass


class _Limiter:
    def __init__(self, limit: int):
        self.left = limit

    def __call__(self, frame, event, arg):
        self.left -= 1
        if self.left <= 0:
            raise StepLimitExceeded("step limit exceeded")
        return self

    def __enter__(self):
        sys.settrace(self)
        return self

    def __exit__(self, *exc):
        sys.settrace(None)
        return False


def module_order(files: dict) -> list:
    """Workspace .py modules in static-import dependency order (imports of
    other workspace modules first; cycles broken by name order)."""
    names = {p[:-3] for p in files if p.endswith(".py")}
    deps = {}
    for p, content in files.items():
        if not p.endswith(".py"):
            continue
        found = set()
        for m in re.finditer(r"^\s*(?:import|from)\s+([a-z_][a-z0-9_]*)",
                             content, re.MULTILINE):
            if m.group(1) in names:
                found.add(m.group(1))
        deps[p[:-3]] = found
    out, seen = [], set()

    def visit(n, stack):
        if n in seen or n in stack:
            return
        stack.add(n)
        for d in sorted(deps.get(n, ())):
            visit(d, stack)
        stack.discard(n)
        seen.add(n)
        out.append(n)

    for n in sorted(deps):
        visit(n, set())
    return out


def load_workspace(files: dict) -> dict:
    """name -> namespace dict, or an Exception where the module failed."""
    modules: dict = {}

    def _import(name, *args, **kwargs):
        if name in modules and not isinstance(modules[name], Exception):
            import types
            mod = types.ModuleType(name)
            mod.__dict__.update(modules[name])
            return mod
        raise ImportError(f"module {name!r} is not available in the workspace")

    for name in module_order(files):
        source = files[name + ".py"]
        ns = {"__builtins__": {**_SAFE_BUILTINS, "__import__": _import},
              "__name__": name}
        try:
            code = compile(source, name + ".py", "exec")
            with _Limiter(STEP_LIMIT):
                exec(code, ns)
            modules[name] = ns
        except Exception as e:          # noqa: BLE001 - any failure = broken module
            modules[name] = e
    return modules


def call(modules: dict, module: str, fn: str, args: list):
    """(ok, value_or_error).  Deterministic, step-limited."""
    ns = modules.get(module)
    if ns is None or isinstance(ns, Exception):
        return False, f"module {module} broken"
    f = ns.get(fn)
    if not callable(f):
        return False, f"{module}.{fn} is not callable"
    try:
        with _Limiter(STEP_LIMIT):
            return True, f(*[_thaw(a) for a in args])
    except Exception as e:              # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _thaw(x):
    """JSON structures arrive as shared objects; give each call fresh copies."""
    if isinstance(x, dict):
        return {k: _thaw(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_thaw(v) for v in x]
    return x
