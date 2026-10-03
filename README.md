# gpml-conformance

An executable reference semantics for the path-pattern core of **GPML** — the graph
pattern matching language shared by **GQL** (ISO/IEC 39075:2024) and **SQL/PGQ**
(ISO/IEC 9075-16:2023) — and the first answer-level divergence map placing shipping
property-graph engines against it.

Three questions, none of them previously measured:

1. **When engines run the same standard-defined pattern, do they return the same
   answer?** No. The matrix below says exactly where.
2. **When they disagree, is the user told?** That depends entirely on the engine, and
   the spread is the finding: one engine never disagrees silently, three always do.
3. **Does an engine refuse what the standard makes ill-formed?** Mostly yes -- and the
   one that does not, answers it with a different mode's answer.

<!-- BEGIN GENERATED: scorecard -->

**84 constructs x 13 engines = 1092 cells.** Each cell is one exact multiset comparison, run 3 times to confirm the engine agrees with itself.

| engine | version | conforms | diverges | rejects | inexpressible | silence ratio | refuses ill-formed |
|---|---|---:|---:|---:|---:|---:|---:|
| kuzu | 0.11.3 | 33 | 15 | 1 | 29 | 0.94 | not askable |
| ladybugdb | 0.21.2 | 33 | 15 | 1 | 29 | 0.94 | not askable |
| duckpgq | 1.4.1 | 10 | 28 | 40 | 0 | 0.41 | 3/3 |
| neo4j | Neo4j Kernel 5.26.30 | 45 | 10 | 0 | 23 | 1.00 | 3/3 |
| neo4j-2026 | Neo4j Kernel 2026.04.0 | 46 | 9 | 23 | 0 | 0.28 | 3/3 |
| memgraph | Memgraph 5.9.0 | 39 | 10 | 0 | 29 | 1.00 | not askable |
| apache-age | age 1.8.0 | 38 | 10 | 1 | 29 | 0.91 | not askable |
| arcadedb | 26.9.1 | 42 | 27 | 9 | 0 | 0.75 | 3/3 |
| falkordb | falkordb 8.10.2 | 39 | 10 | 0 | 29 | 1.00 | not askable |
| surrealdb | surrealdb-3.3.0 | 51 | 6 | 4 | 17 | 0.60 | 0/3 |
| spanner | cloud-spanner-emulator 1.5.58 | 36 | 0 | 25 | 17 | 0.00 | 3/3 |
| grafeo | grafeo 0.5.40 | 59 | 18 | 1 | 0 | 0.95 | not askable |
| samyama-graph *(ours)* | samyama v1.10.0 | 68 | 10 | 0 | 0 | 1.00 | 3/3 |

Over every engine but ours and the superseded Neo4j line: **S1 = 0.2578** of answered cells diverge, and **S2 = 0.585** of disagreements are silent -- the query runs, returns a different multiset, raises nothing. The silence ratio is a property of the engine, not of the problem: the table above spans the whole range from 0 to 1.

The standard defines 16 restrictor x selector combinations. Over an exhaustive sweep of 22,474 directed multigraphs, 114 of 120 cell pairs have a separating witness and 6 have none: **12 of 16 combinations are observably different.** A shortest path is already simple, so the restrictor is unobservable under a shortest selector except for ACYCLIC.

<!-- END GENERATED: scorecard -->

Everything in that block is written by `src/summarise.py` from `results/summary.json`.
No number in this README is typed by hand, because a README that restates a measurement
is a second copy of it, and the two drift.

## What is here

| Path | What it is |
|---|---|
| `src/gpml_ref.py` | The reference semantics. Restrictors (WALK/TRAIL/ACYCLIC/SIMPLE), selectors (ALL/ANY/ALL SHORTEST/ANY SHORTEST), quantified segments. Consults no engine. |
| `src/suite.py` | The 17 hand-picked v1 cases, ids unchanged. |
| `src/suite_v2.py`, `src/render.py` | The v2 matrix: cases generated from declared dimensions, and the renderers that spell one construct in each dialect. See `docs/MATRIX-v2.md`. |
| `src/suite_all.py` | What the runner executes: v1 plus v2, deduplicated, every case carrying the clause it tests. |
| `tools/separation.py` | Which of the standard's 16 restrictor x selector combinations any graph can tell apart. Answer: 12. |
| `tools/choose_beds.py` | Derives the fixture beds the grid runs on, by separation rather than by taste. |
| `tools/verify_adapter.py` | Gate A: does an adapter transport the graph faithfully? A new engine passes this before its divergences mean anything. |
| `src/level2.py`, `src/run_level2.py` | Compares multisets of **edge sequences**, not just endpoint pairs — the resolution the headline comparison gives up. |
| `src/diagnostics.py` | Classifies what an engine said beside an answer, and re-tests whether the claim was true. |
| `src/metamorphic.py` | Three relations that hold under *every* path mode, so they need no reference at all. |
| `src/engines_adapters.py` | Adapters for every engine in the matrix. Adding one is one class: see `ADDING-AN-ENGINE.md`. |
| `docs/PREREGISTRATION-v2.md` | What was fixed before the run, what was not, and the disclosure that the v2 dimensions were chosen by people who already knew the v1 results. |
| `tests/` | Gate B: the reference must reproduce the worked answers published in the standard's reference exposition. |
| `reproducers/` | Standalone minimal reproducers for each engine defect found. |
| `RESULTS.md` | Generated. The map and the statistics. |

## The oracle is not another engine

Differential testing across engines can only tell you that two systems disagree, not
which is right. The yardstick here is the standard itself, made executable:
`src/gpml_ref.py` implements the definitions in

> A. Deutsch, N. Francis, A. Green, K. Hare, B. Li, L. Libkin, T. Lindaaker,
> V. Marsault, W. Martens, J. Michels, F. Murlak, S. Plantikow, P. Selmer,
> O. van Rest, H. Voigt, D. Vrgoč, M. Wu, F. Zemke.
> *Graph Pattern Matching in GQL and SQL/PGQ*. SIGMOD 2022. arXiv:2112.06217.

written by members of the standards committee. That paper prints the exact path
bindings six of its worked queries return. **`tests/test_gate_b_paper_examples.py`
requires the reference to reproduce all six before any engine is measured.** It caught
a real bug in the first implementation: intermediate nodes under a quantifier were
being over-constrained.

## Reproduce

> **Give this room, or cap it.** The metamorphic layer asks quantifier-range
> decompositions over deliberately pathological small fixtures — self-loops and
> 2-cycles. An engine that mishandles them can grow without bound on a graph of 2 nodes
> and 3 edges: that is how `samyama-graph#1183` was found, and it killed a 46 GB
> workstation several times before the shape was visible. The measured peak for the
> engines in the current run is in `RESULTS.md`.
>
> On a smaller machine, cap the run so a runaway dies alone instead of taking the
> session with it:
>
> ```bash
> systemd-run --user --scope -p MemoryMax=12G ./run.sh
> ```
>
> An exit code of 137 then means the cap did its job. No other engine in the suite
> exceeded 800 MB.

```bash
./run.sh          # starts the engines in Docker, runs everything, regenerates RESULTS.md
```

Or step by step:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

docker run -d --name cf-neo4j    -p 7688:7687 -e NEO4J_AUTH=neo4j/testpassword123 neo4j:5.26-community
docker run -d --name cf-memgraph -p 7689:7687 memgraph/memgraph:latest
docker run -d --name cf-age      -p 5433:5432 -e POSTGRES_PASSWORD=postgres apache/age:latest

pytest tests/ -q                 # Gate B -- must pass first
python src/run_map.py            # the conformance map
python src/run_metamorphic.py    # the oracle-free layer
python src/summarise.py          # regenerates RESULTS.md
```

`duckdb` is pinned to 1.4.1 because the DuckPGQ community extension is not built for
every DuckDB release.

## Scoring, and what it does not claim

Each cell gets one of: `CONFORMS`, `DIVERGES`, `REJECTS`, `INEXPRESSIBLE`.

- **A dialect without syntax for a construct scores `INEXPRESSIBLE`, never a failure.**
  openCypher has no `ACYCLIC` keyword; that is a fact about the language, not a defect.
- **Nondeterminism is never scored as divergence.** `ANY` and `ANY SHORTEST` fix how
  many paths come back per endpoint pair, not which ones, so those cells are checked
  against the admissible set and the per-partition count.
- **Every divergence is scored twice**: against the ISO reference, and against the path
  mode the engine's own manual declares. A divergence explained by the engine's own
  documentation is a *language* difference. Only the rest are defects.

Nine of the fifteen divergences are documented language differences. Six are not.

This repository measures **meaning only**. It contains no timing number and makes no
claim about performance.

## Conflict of interest

This work was produced at Samyama, which develops one of the engines measured. It is
measured at its published release, **`v1.8.0`** — every other row is a published release
too — and our row is excluded from every aggregate. No engine's output derives any
expected answer.

**`v1.8.0` carries fixes this suite prompted.** Our maintainers are the authors and saw
every finding before this release shipped; no other engine's maintainers had that
chance. That is the standing caveat, and it is why our row enters no total. See
[`OUR-ENGINE.md`](OUR-ENGINE.md) for the issues and the builds.

## Licence

Apache-2.0. See `LICENSE`.
