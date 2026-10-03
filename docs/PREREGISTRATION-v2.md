---
title: "Stage 2 amendment — pre-registration for the widened matrix"
date: 2026-10-03
amends: PREREGISTRATION.md (2026-09-07)
mode: "(b) artifact-first, effect-agnostic characterisation -- unchanged"
frozen_after: "the v1 results were known; see Disclosure"
---

# Pre-registration, v2

This amends the 2026-09-07 pre-registration. Everything in the original stands unless
contradicted here. The registered object is still a map, not a direction.

## Disclosure, first

This amendment is **not** blind. The v1 results are published (arXiv:2609.23032) and
known to the authors, so the v2 dimensions were chosen by people who already knew where
v1 found divergence. Three things keep that from steering the result:

1. **The dimensions are enumerated, not selected.** G1 is every restrictor crossed with
   every selector -- all 16, not the interesting ones. G2 is every quantifier form in
   the standard's grammar that the oracle can evaluate. Leaving out a cell would require
   leaving out a whole dimension, and the dimensions are listed here before the run.
2. **The fixture beds are chosen by a published rule, not by eye.** `tools/choose_beds.py`
   maximises the number of grid-cell pairs a bed separates, ties broken by the smallest
   total answer size. The rule runs before the engines do and its output is committed.
3. **The one group that is post-hoc says so.** G5 was added after the first v2 run. It is
   reported apart from the pre-registered groups and is never folded into the headline.

## What is added

| group | content | cells | fixed before any v2 run |
|---|---|---|---|
| G1 | restrictor x selector, all 16, on two beds | 32 | yes |
| G2 | quantifier form x restrictor | 14 | yes |
| G3 | pattern shape x restrictor | 12 | yes |
| G4 | patterns the standard requires to be rejected, with accept controls | 6 | yes |
| G5 | spelling equivalences | 4 | **no -- post-hoc, see Disclosure** |
| v1 | the original 17, ids unchanged | 17 | n/a |

Full design in the artifact at `docs/MATRIX-v2.md`.

## New verdict rules

The four v1 verdicts are unchanged. Two additions:

- **A case carries an expectation.** `ANSWER` (compare to the reference, the default and
  every v1 case), `REJECT` (the standard makes the pattern ill-formed; refusing it is the
  conforming act), `ACCEPT` (the pattern is well-formed and must not be refused).
- **Under `REJECT`, a refusal scores CONFORMS and an answer scores DIVERGES.** Under
  `ACCEPT`, a refusal scores REJECTS rather than DIVERGES: an engine that has not
  implemented TRAIL refuses the control for a reason unrelated to the rule being tested,
  and scoring that a divergence would charge it twice for one gap.

## New registered statistics

S1, S2 and S3 are unchanged and are reported over the same population as v1 so the two
runs stay comparable, plus over the widened population, both labelled.

- **S4 -- well-formedness enforcement.** Of the (G4 REJECT case, engine) cells where the
  engine could be asked at all, the fraction refused. Reported with the accept-control
  result beside it, because an engine that refuses everything scores 1.0 on S4 alone.
- **S5 -- spelling self-contradiction.** For each G5 pair and engine, whether the two
  spellings of one quantifier returned the same answer. Reported per engine, never
  aggregated into a rate: with four cases a rate is a count wearing a decimal point.
- **S6 -- observable classes.** The number of (restrictor, selector) combinations that
  any graph can tell apart, from `tools/separation.py`. Reported with the sweep size.
  This is a property of the standard, not of any engine, and it bounds what S3 can mean:
  a construct cannot show more answer classes than the semantics has.

## Pre-declared, so it cannot be claimed afterwards

- **S1 will rise or fall and either is reported.** Widening the matrix adds cells where
  engines conform (the whole of G4's reject direction, most of G2) and cells where they
  do not (every WALK cell, now eight constructs instead of two). The direction of the
  change is not predicted here and will not be presented as a finding on its own.
- **A divergence count is not the finding.** Eight constructs now fail for one cause --
  openCypher's relationship-uniqueness rule is TRAIL, not WALK. The headline is the
  number of distinct causes, not the number of red cells, and the attribution split
  (documented difference vs departure from the engine's own manual) carries it.
- **Engines are added for coverage of the standard's surface, not for their results.**
  The additions were decided from a capability survey -- which engines ship path modes,
  selectors or quantified patterns at all -- before any of them was run. An engine that
  turns out to conform everywhere stays in the matrix and is reported.

## Kill criteria, restated

- **Killed** if the widened suite cannot be driven end to end against at least the six
  engines v1 measured. (Not killed: v1's engines all ran.)
- **Killed** if Gate B regresses. The oracle is unchanged in v2 and still reproduces 6/6
  of the published worked answers; any change to `src/gpml_ref.py` re-opens Gate B.
- **Re-scoped, not killed**, if the widening finds no new cause. The paper then reports a
  wider map with the same two causes, which is a stronger negative than v1 could make.

## Conflict of interest

Unchanged. Samyama-Graph is ours, measured by the same suite at the release a user can
install, reported as one row, excluded from every headline statistic, and disclosed.
Nothing in the engine was changed in response to a v2 cell before this run; if anything
is changed afterwards, the row is re-measured and both numbers are shown.

## Out of scope, unchanged

Writes, transactions, DDL, aggregation, subqueries, graph construction, and performance
of any kind. No timing number appears in this work.

Newly declared gaps, named so they are not mistaken for coverage: counted selectors
(`ANY k`, `SHORTEST k`), which the reference exposition does not define and the oracle
does not implement; alternation and optional segments; edge label disjunction and
undirected edges, which need a second edge label or edge kind in every adapter.
