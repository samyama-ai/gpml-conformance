# gpml-conformance

An executable reference semantics for the path-pattern core of **GPML** — the graph
pattern matching language shared by **GQL** (ISO/IEC 39075:2024) and **SQL/PGQ**
(ISO/IEC 9075-16:2023) — and the first answer-level divergence map placing shipping
property-graph engines against it.

Two questions, both previously unmeasured:

1. **When five engines run the same standard-defined pattern, do they return the same
   answer?** For 7 of 17 constructs, no.
2. **When they disagree, is the user told?** 60% of the time, no: the query runs and
   returns a different multiset, with no error.

## What is here

| Path | What it is |
|---|---|
| `src/gpml_ref.py` | The reference semantics. Restrictors (WALK/TRAIL/ACYCLIC/SIMPLE), selectors (ALL/ANY/ALL SHORTEST/ANY SHORTEST), quantified segments. Consults no engine. |
| `src/suite.py` | 17 conformance cases: the abstract pattern plus the natural rendering in each dialect. |
| `src/level2.py`, `src/run_level2.py` | Compares multisets of **edge sequences**, not just endpoint pairs — the resolution the headline comparison gives up. |
| `src/diagnostics.py` | Classifies what an engine said beside an answer, and re-tests whether the claim was true. |
| `src/metamorphic.py` | Three relations that hold under *every* path mode, so they need no reference at all. |
| `src/engines_adapters.py` | Adapters for Kùzu, DuckPGQ, Neo4j, Memgraph, Apache AGE, and Samyama-Graph. |
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

> **Run this on a machine with at least 96 GB of RAM, or cap it.** The metamorphic
> layer asks quantifier-range decompositions over deliberately pathological small
> fixtures — self-loops and 2-cycles. Samyama-Graph **v1.7.1** grows without bound on
> one of them and was measured at a **75 GB** peak, on a graph of 2 nodes and 3 edges
> (`samyama-graph#1183`; fixed on that engine's `main`, not in the release the suite
> measures). It killed a 46 GB workstation several times before the shape was visible.
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

This work was produced at Samyama, which develops one of the engines measured. The
comparison measures **the release, `v1.7.1`** — every other row is a published release
too — and both our rows are excluded from every aggregate. No engine's output derives
any expected answer.

`v1.7.1` predates every fix this suite prompted, so the row shows the engine as shipped,
which scores worse than our development head. That is deliberate. See
[`OUR-ENGINE.md`](OUR-ENGINE.md) for the issues, the builds, and the standing caveat.

## Licence

Apache-2.0. See `LICENSE`.
