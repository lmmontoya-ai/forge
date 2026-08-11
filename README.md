# FORGE

**A three-seat collaborative build environment for language-model agents.**

Three agents (API, DATA, QA) build one small software service against a deadline. Each holds a private fragment of the specification, a hidden acceptance suite rewards combining the fragments, matching tests reward nothing except agreeing with each other, and shared budgets (test runs, probes, release tokens, the clock) are scarce enough that negligence and unilateralism have real victims.

The whole world is a deterministic state machine over an append-only event log: every state is a fold, every prompt is a pure function of the log, and any moment of any episode replays byte-for-byte.

FORGE is the second world of a two-environment confirmatory package with [LEDGER](../ledger). It shares LEDGER's technical stack and architectural discipline: frozen machine-readable specs, a pure core with no LLM dependency, pure rendering with field manifests and digests, an impure runtime confined to one directory, and scripted policies for probes and baselines.

## Documents

- [`docs/FORGE_ENVIRONMENT_DESIGN.md`](docs/FORGE_ENVIRONMENT_DESIGN.md) — the world: seats, fragments, convention slots, contracts, the amendment, harm grading, what an agent sees.
- [`docs/IMPLEMENTATION_DECISIONS.md`](docs/IMPLEMENTATION_DECISIONS.md) — every place the design left a choice genuinely unspecified, and the reading the implementation takes.
- [`docs/IMPLEMENTATION_REPORT.md`](docs/IMPLEMENTATION_REPORT.md) — what was built, how it maps to the design, and validation status.

## Repository layout

```
spec/                frozen machine-readable action, tool, slot, and template definitions
src/forge/core       pure world: events, fold, actions, contracts, workspace, budgets, releases
src/forge/grading    pure grading: sandboxed suite runner, Cap, dependency map, harm, REPORT verdicts
src/forge/slots      pure Schelling subsystem: extractors, matching, stakes
src/forge/scenarios  generate, audit, admit, freeze
src/forge/render     pure rendering: state -> bytes -> digest, all view variants
src/forge/runtime    the only code that touches a provider
src/forge/policies   scripted seats for probes, audits, baselines
tests/               golden, property, integration
banks/               frozen scenario banks
```

## Quick start

```
python -m pytest tests
python scripts/run_episode.py --bank v1 --index 0 --api scripted:builder --data scripted:builder --qa scripted:prober --out data/runs/smoke
```
