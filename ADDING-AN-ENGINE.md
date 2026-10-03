# Adding an engine

An engine joins the matrix by adding one class. There is no registry, no plugin system
and no configuration file. If your engine speaks Bolt you may not need to write anything
at all.

## 1. Write the adapter

Four members, in `src/engines_adapters.py`:

```python
class MyAdapter:
    name = "myengine"           # the column heading in the map
    dialect = "cypher"          # "cypher", "gql" or "pgq" -- see below

    def __init__(self, ...):
        self.version = ...      # what the engine reports, not what you expect

    def load(self, g, primary, edge_label):
        """Put the fixture in. Called once per fixture, before any query."""

    def run(self, q) -> Answer:
        """Run one query. Return _counter(rows). Raise EngineError if refused."""
```

`load` receives a `PropertyGraph` with `.nodes` and `.edges`; `primary` and `edge_label`
are the node and edge label that fixture uses. `run` gets a query already written in
your dialect and must return the rows as `(s, t)` pairs. A refusal must raise
`EngineError` -- it is a verdict, not a crash, and swallowing it turns a visible
rejection into a silent wrong answer.

### Which dialect

One construct, four spellings. Pick the one your engine parses:

| `dialect` | example | engines |
|---|---|---|
| `cypher` | `-[:E*1..3]->` | Neo4j, Memgraph, Apache AGE, Kuzu, FalkorDB, ArcadeDB |
| `gql` | `-[:E]->{1,3}` | SurrealDB, Spanner Graph |
| `pgq` | `GRAPH_TABLE(g MATCH ...)` | DuckPGQ |

`cypher` engines are probed at run time (`src/capabilities.py`) for whether they also
take the standard's restrictor and selector prefixes, and in which of the two spellings.
You do not declare that; it is measured.

If your engine speaks Bolt, `BoltAdapter` already works -- pass it a name and a URI.

## 2. Pass Gate A

```
make verify-adapter ENGINE=myengine
```

Gate A asks only questions whose answers do not depend on path semantics: that every
node arrived, that the one-hop endpoint multiset equals the edge list (which catches
dropped parallel edges, lost self-loops and reversed directions in one check), and that
the reverse direction is not symmetric with the forward one.

This gate exists because a wrong loader and a non-conforming engine produce the same
symptom. Until Gate A passes, a divergence in your engine's column is more likely to be
your adapter than your engine, and the map would publish it as a finding. **A pull
request that adds an engine must show Gate A passing on all six fixtures.** All eleven
current adapters do.

## 3. Declare the engine's own semantics

Add an entry to `DECLARED_MODE` in `src/run_map.py`. This is the second axis of the map:
it separates a divergence the engine's own manual predicts (a *language* difference,
which a user can look up) from one it does not (an *implementation* difference, which a
user cannot).

| value | meaning |
|---|---|
| `"WALK"` / `"TRAIL"` / ... | the path mode the engine's documentation assigns to an unprefixed variable-length pattern |
| `None` | the dialect **is** the standard, so there is no second axis |
| `"UNDOCUMENTED"` | the engine publishes no rule, so a divergence here cannot be excused by a manual |

Cite the documentation in the comment. A declared mode with no citation is an
assumption, and the map would present it as a fact.

## 4. Start it in `run.sh`

Every engine with a row has to be started by `./run.sh`. A row whose container `run.sh`
does not start scores `LOAD_FAILED` across the board and the map ships with a hole in it.

## 5. Run it

```
./run.sh
```

brings the engines up, gates the oracle against the standard's six published answers,
runs the map, the level-2 refinement and the metamorphic layer, and regenerates
`RESULTS.md` and `results/summary.json`.

## What we will not do

- **Tune a query to make an engine look better.** Each construct has one natural
  spelling per dialect, produced by `src/render.py` from the construct itself. If your
  engine needs a different spelling, that is a dialect difference and belongs in the
  renderer, where every engine on that dialect gets it.
- **Score a missing feature as a divergence.** A dialect with no `ACYCLIC` keyword is
  not wrong about ACYCLIC; it is silent, and silence scores `INEXPRESSIBLE` and is
  excluded from S1 and S2.
- **Call nondeterminism a divergence.** `ANY` and `ANY SHORTEST` are checked against the
  admissible set and the per-partition count, never against one chosen path.
- **Measure an unreleased build.** Every row is the release a user can install,
  including ours.
