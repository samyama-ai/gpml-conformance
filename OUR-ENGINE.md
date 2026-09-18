# The authors' own engine

The suite measures Samyama-Graph, which the authors develop. This file states how that
is handled, so the choice is visible rather than buried in a runner flag.

## Which build is measured, and why

**Both published releases are measured: `v1.8.0` (2026-09-15) and `v1.7.1` (2026-08-27).**
Every row in the paper is a release a reader can install. Ours are two rows for the same
reason Neo4j is two rows: a version pair is what shows drift. `v1.8.0` is the newest and
is the row the comparison uses; `v1.7.1` is superseded and excluded from the headline
aggregate on the same rule that excludes Neo4j 5.26.

**No development head is measured.** No other vendor's unreleased work is, so measuring
ours would not be the same comparison.

`SAMYAMA_BIN` and `SAMYAMA_BUILD` select the newest release; `SAMYAMA_PREV_BIN` and
`SAMYAMA_PREV_BUILD` add the prior release as the `samyama-graph-171` row.

## What v1.8.0 changed

`v1.7.1` was the release when this suite was first run, and the suite found real defects
in it. Every one was fixed on the engine's main branch and **all of them ship in
`v1.8.0`**:

| issue | what it was |
|---|---|
| [#1140](https://github.com/samyama-ai/samyama-graph/issues/1140) | a quantifier with lower bound 0 collapsed the path multiset to one row per reachable end node |
| [#1141](https://github.com/samyama-ai/samyama-graph/issues/1141) | the GQL path restrictors and selectors were not implemented |
| [#1143](https://github.com/samyama-ai/samyama-graph/issues/1143) | an integrity check, `CALL db.checkIntegrity()` |
| [#1148](https://github.com/samyama-ai/samyama-graph/issues/1148) | `MATCH TRAIL p = (...)`, the order the standard's own examples use, did not parse |
| [#1149](https://github.com/samyama-ai/samyama-graph/issues/1149) | a notification when an unwritten path mode changed the answer |
| [#1183](https://github.com/samyama-ai/samyama-graph/issues/1183) | 75 GB peak on a 2-node, 3-edge graph |

**This is the reason the two rows differ, and a reader should weigh it.** The suite's
findings reached this engine's maintainers first, because they are the authors. No other
engine's maintainers had that chance before their measured release shipped. The v1.7.1
row is kept precisely so the improvement is visible as a before, not asserted.

## What does not depend on this

No engine's output, ours included, derives any expected answer. Every expected answer
comes from `src/gpml_ref.py`, which implements the standard and never consults a
database, and which must reproduce the six worked answers published in the standard's
reference exposition before any engine is measured (`tests/`).

Both our rows are excluded from every aggregate in `RESULTS.md` and in the paper.

## v1.7.1 also exhausted memory on a two-node graph

Measured while running this suite on a 128 GB machine: `v1.7.1` peaked at **75 GB**
during the metamorphic layer. The minimal case is 2 nodes and 3 edges -- a self-loop
`x->x`, plus `x->y` and `y->x` -- asked `MATCH p=(x:N)-[:E*1..2]->(y:N)`. Under TRAIL
that has a handful of paths.

| build | result |
|---|---|
| v1.7.1 | exceeds a 6 GB cap; 75 GB peak under the full suite |
| v1.8.0 | see `RESULTS.md` for the measured peak on the same case |

Filed as [samyama-graph#1183](https://github.com/samyama-ai/samyama-graph/issues/1183)
and shipped fixed in `v1.8.0`. On `v1.7.1` it is a denial of service reachable from an
ordinary read query, and `v1.7.1` was the only release for the nineteen days between the
two.

This is worth stating plainly because it is a *finding of the suite*, not a limitation
of it. The corpus that exposes it -- pathological small fixtures at quantifier bounds --
is exactly what the engine's own test suite did not contain.
