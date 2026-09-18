# The authors' own engine

The suite measures Samyama-Graph, which the authors develop. This file states how that
is handled, so the choice is visible rather than buried in a runner flag.

## Which build is measured, and why

**The comparison measures the release, `v1.8.0`.** Every row in the paper is a release a
reader can install. No development head is measured: no other vendor's unreleased work
is, so measuring ours would not be the same comparison.

`SAMYAMA_BIN` and `SAMYAMA_BUILD` select it.

## The standing caveat

`v1.8.0` carries fixes this suite prompted: a quantifier with lower bound 0 that
collapsed the path multiset ([#1140](https://github.com/samyama-ai/samyama-graph/issues/1140)),
the GQL path restrictors and selectors ([#1141](https://github.com/samyama-ai/samyama-graph/issues/1141)),
an integrity check ([#1143](https://github.com/samyama-ai/samyama-graph/issues/1143)),
`MATCH TRAIL p = (...)` ([#1148](https://github.com/samyama-ai/samyama-graph/issues/1148)),
a path-mode notification ([#1149](https://github.com/samyama-ai/samyama-graph/issues/1149)),
and unbounded memory growth on a 2-node graph ([#1183](https://github.com/samyama-ai/samyama-graph/issues/1183)).

**Our maintainers are the authors and saw every finding before this release shipped. No
other engine's maintainers had that chance.** That is the reason to read our row with
suspicion, and it is why our row enters no total. It is not evidence about the engine
against the others; it is evidence that the suite finds real defects.

## What does not depend on this

No engine's output, ours included, derives any expected answer. Every expected answer
comes from `src/gpml_ref.py`, which implements the standard and never consults a
database, and which must reproduce the six worked answers published in the standard's
reference exposition before any engine is measured (`tests/`).

Both our rows are excluded from every aggregate in `RESULTS.md` and in the paper.

## What the suite found here that a normal test suite did not

The metamorphic layer asks quantifier-range decompositions over deliberately
pathological small fixtures -- self-loops and 2-cycles. On a graph of 2 nodes and 3
edges, `MATCH p=(x:N)-[:E*1..2]->(y:N)` grew without bound: a denial of service
reachable from an ordinary read query
([#1183](https://github.com/samyama-ai/samyama-graph/issues/1183)).

That corpus is exactly what the engine's own test suite did not contain. The finding is
a *finding of the suite*, not a limitation of it.
