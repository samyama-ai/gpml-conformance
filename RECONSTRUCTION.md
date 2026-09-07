# Reconstructing the Figure 1 Transfer sub-graph

The oracle is validated (Gate B) against the worked answers printed in Sec. 5.1 of
Deutsch et al., *Graph Pattern Matching in GQL and SQL/PGQ* (SIGMOD 2022,
arXiv:2112.06217). Those answers are over the property graph of the paper's Figure 1,
which is a figure, not text. The `Transfer` sub-graph is recovered from the paths the
paper itself prints — every edge below is witnessed by a printed path.

| Edge | From | To | Witnessed by |
|---|---|---|---|
| `t1` | `a1` | `a3` | `path(a6,t6,a5,t8,a1,t1,a3,t2,a2)` |
| `t2` | `a3` | `a2` | `path(a6,t5,a3,t2,a2)` |
| `t3` | `a2` | `a4` | `path(a6,t5,a3,t2,a2,t3,a4,t4,a6,...)`; also Fig. 2's `Transfer` row `t3 a2 a4` |
| `t4` | `a4` | `a6` | same path |
| `t5` | `a6` | `a3` | `path(a6,t5,a3,t2,a2)` |
| `t6` | `a6` | `a5` | `path(a6,t6,a5,t8,a1,t1,a3,t2,a2)` |
| `t7` | `a3` | `a5` | `path(a3,t7,a5,t8,a1,t1,a3)` (the "Transfer loop" of Sec. 5) |
| `t8` | `a5` | `a1` | same |

Owners are recovered from the queries and their answers:

| Account | Owner | Recovered from |
|---|---|---|
| `a6` | Dave | `(a WHERE a.owner='Dave')-[t:Transfer]->*` answers all start at `a6` |
| `a2` | Aretha | the same query's answers all end at `a2` |
| `a3` | Mike | `ALL SHORTEST TRAIL ... (Aretha)-[r]->*(Mike)` answers end at `a3`; Fig. 2 lists `a3 Mike no` |
| `a5` | Natalia | the `{1,10}` example's solution starts at `a5` |
| `a1` | Scott | the same solution ends at `a1` |
| `a4` | Charles | the only remaining account; used only as an interior node, so the name is immaterial to every test |

**Why this is sound.** The reconstruction is not asserted, it is *tested*: six independent
published answers — three TRAIL bindings, one excluded non-trail, two ALL SHORTEST TRAIL
bindings, one ANY SHORTEST binding, and one WALK-vs-restrictor case — all come out exactly
right under this graph. A wrong edge set would break at least one of them.
