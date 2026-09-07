# gpml-conformance

An executable reference semantics for the path-pattern core of **GPML** — the graph
pattern matching language shared by **GQL** (ISO/IEC 39075:2024) and **SQL/PGQ**
(ISO/IEC 9075-16:2023) — and the first answer-level divergence map placing shipping
property-graph engines against it.

Two questions, both previously unmeasured:

1. **When five engines run the same standard-defined pattern, do they return the same
   answer?** For 8 of 17 constructs, no.
2. **When they disagree, is the user told?** 60% of the time, no: the query runs and
   returns a different multiset, with no error.

## What is here

| Path | What it is |
|---|---|
| `src/gpml_ref.py` | The reference semantics. Restrictors (WALK/TRAIL/ACYCLIC/SIMPLE), selectors (ALL/ANY/ALL SHORTEST/ANY SHORTEST), quantified segments. Consults no engine. |
| `src/suite.py` | 17 conformance cases: the abstract pattern plus the natural rendering in each dialect. |
| `src/metamorphic.py` | Three relations that hold under *every* path mode, so they need no reference at all. |
| `src/engines_adapters.py` | Adapters for Kùzu, DuckPGQ, Neo4j, Memgraph, Apache AGE. |
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

This work was produced at Samyama, which develops a property-graph engine. That engine
is measured by the same suite, reported as one row, and excluded from the headline
statistics. No engine's output was used to derive any expected answer.

## Licence

Apache-2.0. See `LICENSE`.
