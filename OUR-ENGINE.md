# The authors' own engine

The suite measures Samyama-Graph, which the authors develop. This file states how that
is handled, so the choice is visible rather than buried in a runner flag.

## Which build is measured, and why

**The comparison measures the release, `v1.7.1`.** Every other row in the table is a
published release a reader can install; measuring ours at a development head would not
be the same comparison.

That matters here more than it usually would, because the development head carries
fixes this suite prompted:

| issue | what it was |
|---|---|
| [#1140](https://github.com/samyama-ai/samyama-graph/issues/1140) | a quantifier with lower bound 0 collapsed the path multiset to one row per reachable end node |
| [#1141](https://github.com/samyama-ai/samyama-graph/issues/1141) | the GQL path restrictors and selectors were not implemented |
| [#1143](https://github.com/samyama-ai/samyama-graph/issues/1143) | an integrity check, `CALL db.checkIntegrity()` |
| [#1148](https://github.com/samyama-ai/samyama-graph/issues/1148) | `MATCH TRAIL p = (...)`, the order the standard's own examples use, did not parse |
| [#1149](https://github.com/samyama-ai/samyama-graph/issues/1149) | a notification when an unwritten path mode changed the answer |

**None of that is in `v1.7.1`**, which was released 2026-08-27, before any of it. So the
row in the comparison is the engine as shipped — which scores worse, and is the honest
number.

To measure the development head as well, set `SAMYAMA_DEV_BIN` to a second binary. It is
reported as a separate row, `samyama-graph-dev`, and is excluded from every aggregate,
exactly as the release row is. Nothing about it enters the comparison, because no other
vendor's unreleased work is measured either.

## What does not depend on this

No engine's output, ours included, derives any expected answer. Every expected answer
comes from `src/gpml_ref.py`, which implements the standard and never consults a
database, and which must reproduce the six worked answers published in the standard's
reference exposition before any engine is measured (`tests/`).

Both our rows are excluded from every aggregate in `RESULTS.md` and in the paper.

## The standing caveat

The suite found real defects in our engine and they were fixed within a day, because the
maintainers are the authors. No other engine's maintainers have had that opportunity.
Measuring the release rather than the development head is what keeps the table
comparable despite that — but a reader should still know it is the reason the release
row and the dev row differ as much as they do.

## The release also exhausts memory on a two-node graph

Measured while running this suite on a 128 GB machine: `v1.7.1` peaked at **75 GB**
during the metamorphic layer. The minimal case is 2 nodes and 3 edges — a self-loop
`x->x`, plus `x->y` and `y->x` — asked `MATCH p=(x:N)-[:E*1..2]->(y:N)`. Under TRAIL
that has a handful of paths.

| build | result |
|---|---|
| v1.7.1 (released) | exceeds a 6 GB cap; 75 GB peak under the full suite |
| main `717cde3` | 4 rows, 0.0 s, 20 MB peak |

Filed as [samyama-graph#1183](https://github.com/samyama-ai/samyama-graph/issues/1183).
It is fixed on that engine's `main` and present in the release this suite measures,
which is the same gap the conformance rows show, in a more consequential form: on the
released engine it is a denial of service reachable from an ordinary read query.

This is worth stating plainly because it is a *finding of the suite*, not a limitation
of it. The corpus that exposes it — pathological small fixtures at quantifier bounds —
is exactly what the engine's own test suite does not contain.
