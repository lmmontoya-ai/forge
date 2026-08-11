# FORGE spec findings

Places where FORGE_ENVIRONMENT_DESIGN v0.3 is in tension with itself or
with its own parameters, discovered by implementation. In every case the
verbatim reading was implemented and the tension is recorded rather than
silently resolved — the LEDGER `M0_SPEC_FINDINGS` discipline.

## F-A. Profitable exposure (§12.3.5) is numerically unreachable at b = 1/4

**Trace.** Admission requires scripted probes to reach at least two states
where one legal action carries Δ_j moderate-or-major for a victim AND
BP_i > 0 for the mover. §9.6 defines BP verbatim as the mover's own
attainability change, and §9.1's attainability includes the reachable-gain
term g_i — so BP charges the mover the opportunity cost of everything it
could otherwise still do.

**What the probes find.** Five probe families (saboteur, cooperative, two
class-bankers, early-banker) reach release states with Δ_j moderate for a
victim and BP within roughly 3 J-points of zero — but never above it. The
structural reason: J is common fate, so any mover gain through J is also a
victim gain; the mover-specific components (the b·B bonus, ≤ ~14 points,
and σ = 2 stakes) are smaller than the g-term opportunity cost whenever the
victim's damage is still large enough to grade moderate. Δ-moderate wants
victims rich in foreclosed options (early, resources live); BP > 0 wants
the mover poor in alternatives (late). The two conditions chase each other
off the board.

**Resolution taken.** The check is implemented verbatim and reported
per-scenario; the bank records two verdicts: `admitted_strict` (all eight
checks, currently false for every seed) and `admitted_v0` (without
§12.3.5). The v1 bank ships under `admitted_v0` with this finding attached.

**Paths to closure, for the design's next revision (choices, not
decisions):** raise b toward 1/2 or σ toward 5+ so mover-specific gains can
clear the opportunity cost; or define BP against `step(L, WAIT)` rather
than `L`, netting out the spent move; or define BP on banked terms only
(J, B, stakes of the graded artifact), excluding g from the premium while
keeping it in the victim's Δ. Each choice changes what "harm that pays"
means and should be made deliberately, upstream of any pilot.

## F-B. The flat non-message history bound (§10.4) fails for contract lines

**Trace.** §10.4 bounds a non-message history line at 10 tokens. A
`PROPOSE_IFACE` line carrying two binds, two obligations, and parties
measures ~30–40 tokens under o200k; even an `AGREE` line with its lock
bracket measures 15. This is the same failure LEDGER's v2.5 recorded for
its uniform 8-token claim ("did not survive contact with a tokenizer").

**Resolution taken.** Per-class golden bounds, measured then enforced:
simple lines ≤ 14; consequence-bracket lines ≤ 22; REPORT ≤ 32;
PROPOSE_IFACE ≤ 44; message lines ≤ 56. §10.1's own "~8–48 tok each" range
was already consistent with this; only the §10.4 sentence is not.

## F-C. "Extractor returns non-⊥ on skeletons" (§12.3.3) contradicts the ⊥ placeholder (§3.5)

**Trace.** §3.5 specifies that a forfeiting seat's slot literals stay at
the skeleton placeholder ⊥ — so skeletons must carry ⊥. §12.3.3 requires
extractors to return non-⊥ on skeletons.

**Resolution taken.** "Totality" is read as: the extractor never raises and
returns value-or-⊥ on skeletons; returns non-⊥ on all audit-run (solution)
artifacts; and the COMMIT wiring round-trips (committed value in, same
value extracted). Implemented in admission check 3.
