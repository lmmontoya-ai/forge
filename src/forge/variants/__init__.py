"""Optional prompt variants studied in the paper.

FORGE's default environment (the `principal` mandate, the frozen v1 bank at
D=36) is unchanged by anything here.  These modules add the variants the
paper's Engineering campaigns ran, each selected by a mandate string:

- `hidden_priority`: one private operational priority per seat
  (`priority:P_SHIP`, `priority:P_GUARD`, `priority:P_ALIGN`).
- `inactive_label`: its inactive-label control (`sham:COBALT`, ...).
- `clear_goal`: a later explicit sole-objective variant with its own
  active and inactive arms (`clear-goal:<ID>`, `clear-sham:<LABEL>`).
- `extension`: the longer episode (D=72, budgets doubled, amendment still
  at turn 22, first 36 turns scored) every one of those campaigns used.

Only the mover's private context changes: the Mandate paragraph of its
system block and a reminder appended to its own user prompt.  The engine,
scoring, bank, and every reader render are untouched.  See
`forge.variants.registry` for how mandate strings resolve.
"""
from .extension import PAPER_EXTENSION, EpisodeExtension, extend_scenario
from .registry import is_variant_mandate, mover_reminder, parse_mandate, variant_system_block

__all__ = [
    "PAPER_EXTENSION",
    "EpisodeExtension",
    "extend_scenario",
    "is_variant_mandate",
    "mover_reminder",
    "parse_mandate",
    "variant_system_block",
]
