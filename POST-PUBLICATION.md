# Post-publication note: what changed in our own engine, and what did not

`RESULTS.md` is generated and always shows the current measurement. This file records
the one thing a generated file cannot: what the numbers were before, and what the
current ones do and do not support.

## What the artifact disclosed

The paper discloses that the engine developed by the authors scored worst of the six
measured on 2026-09-07: 8 constructs conforming, 4 diverging, 5 inexpressible, silence
ratio 1.00, and 24 metamorphic violations. Root cause — a quantifier with lower bound 0
collapsing the path multiset to one row per reachable end node — was filed publicly as
[samyama-graph#1140](https://github.com/samyama-ai/samyama-graph/issues/1140).

## What was fixed, and when

| issue | what shipped | PR |
|---|---|---|
| #1140 | lower bound 0 no longer collapses the multiset | samyama-graph#1144 |
| #1141 | GQL path restrictors (WALK/TRAIL/ACYCLIC/SIMPLE) and selectors (ALL/ANY/ALL SHORTEST/ANY SHORTEST) | samyama-graph#1145 |
| #1143 | `CALL db.checkIntegrity()` | samyama-graph#1146 |
| #1142 | three metamorphic relations as a CI gate | samyama-graph#1147 |

Build measured: `samyama-graph` at commit `3cb2461`, reporting version string `1.7.1`.
This is an **unreleased build**. No released version of the engine scores what follows.

| metric | 2026-09-07 | now |
|---|---|---|
| conforming | 8 | 15 |
| diverging | 4 | 2 |
| inexpressible | 5 | 0 |
| S1, divergence rate | 0.33 | 0.12 |
| S2, silence ratio | 1.00 | 1.00 |
| metamorphic violations | 24 | 0 |

## What these numbers do not say

Read the row, not the headline. Three qualifications, all of them load-bearing:

- **5 of the 15 conforming cells are answered through a vendor extension** and are
  marked † in the map. They say the engine can express and compute the construct. They
  are not evidence about the dialect the other five engines share, and a reader
  comparing columns should subtract them before concluding anything about portability.
- **S2 is still 1.00.** Both surviving divergences are silent: the engine returns a
  different answer rather than an error. On the axis this artifact was built to measure
  — whether a user is *told* about a disagreement — nothing improved. Neo4j and
  Memgraph also sit at 1.00.
- **The two divergences are not defects.** `mode-walk-bounded` and
  `walk-revisits-same-edge` both score CONFORMS against the engine's declared TRAIL
  mode; they are the documented openCypher relationship-isomorphism difference, the
  same one Neo4j, Memgraph and Apache AGE show.

## What did not change

The cross-engine result this artifact exists to report **excludes our engine** and is
unaffected: 15 divergences and 10 rejections across the five external engines, S1 0.27,
**S2 0.60**. Re-running the suite after these fixes reproduces every external cell
exactly — 0 verdict differences across 85 external cells. The paper's headline needs no
revision.
