"""FORGE: a three-seat collaborative build environment for language-model agents.

The world is a deterministic state machine over an append-only event log
(design doc §3.3).  `forge.core`, `forge.grading`, `forge.slots`, and
`forge.render` are pure; only `forge.runtime` touches a provider.
"""

ENV_VERSION = "forge-0.1"
