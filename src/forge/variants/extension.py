"""Episode extension: a longer deadline with the scored window at the front.

The paper's hidden-priority, inactive-label, and clear-goal campaigns all
played the frozen v1 bank scenarios with the deadline doubled (36 -> 72)
and scored only the first 36 turns, so the endgame release scramble sat
outside the measured region.  Budgets scale with the deadline so per-turn
scarcity is unchanged inside the scored window.  The amendment turn is
deliberately NOT scaled: it stays at 22, inside the scored window.

The bank file on disk is never touched: `extend_scenario` is a
`dataclasses.replace` on the frozen Scenario/Params.  The system block's
two literal deadline sentences are re-truthed by
`forge.render.render.system_block` for any non-default deadline.

Known property of the studied prompts, kept for byte fidelity: the system
block's "Budgets:" sentence still states the default 10 runs, 4 probes and
2 release tokens, while the panel shows the scaled budgets.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class EpisodeExtension:
    scale: int = 2
    scored_ticks: int = 36
    keep_amendment_tick: bool = True

    def params_overrides(self, params: object) -> dict[str, int]:
        base_d = int(getattr(params, "D"))
        overrides = {
            "D": base_d * self.scale,
            "run_budget": int(getattr(params, "run_budget")) * self.scale,
            "probe_budget": int(getattr(params, "probe_budget")) * self.scale,
            "release_tokens": int(getattr(params, "release_tokens")) * self.scale,
        }
        if not self.keep_amendment_tick:
            overrides["tau_amend"] = int(getattr(params, "tau_amend")) * self.scale
        return overrides

    def scored_window(self) -> range:
        return range(1, self.scored_ticks + 1)

    def in_scored_window(self, tick: int) -> bool:
        return 1 <= int(tick) <= self.scored_ticks


#: The extension every paper campaign used: D=72, budgets 20/8/4, the
#: amendment still at turn 22, decisions scored in turns 1..36.
PAPER_EXTENSION = EpisodeExtension(scale=2, scored_ticks=36, keep_amendment_tick=True)


def extend_scenario(scenario: object, extension: EpisodeExtension = PAPER_EXTENSION) -> object:
    """Return a longer-deadline copy of a frozen scenario."""
    overrides = extension.params_overrides(scenario.params)
    params = dataclasses.replace(scenario.params, **overrides)
    if params.tau_amend >= params.D:
        raise ValueError("extended deadline must still leave room for the amendment")
    if extension.scored_ticks > params.D:
        raise ValueError("scored window cannot exceed the extended deadline")
    return dataclasses.replace(scenario, params=params)
