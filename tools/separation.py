#!/usr/bin/env python3
"""Which (restrictor, selector) combinations can any graph tell apart?

The standard defines 4 restrictors x 4 selectors = 16 combinations. It does not say
whether all 16 are observably different. If two combinations always compute the same
answer, then a conformance cell for one of them cannot fail where the other passes, and
an implementer need not implement them separately.

This searches for a separating witness for each of the 120 unordered pairs: a graph, an
anchor and a quantifier bound on which the two combinations return different answers.
A pair with no witness after an exhaustive sweep of all small graphs is reported as
*unobservable*, with the sweep's size stated so the reader can judge the evidence.

Run:  python3 tools/separation.py [--max-nodes 4] [--max-edges 6]
Writes results/separation.json.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))

from graph import PropertyGraph                      # noqa: E402
from gpml_ref import (EdgePattern, NodePattern, PathPattern,  # noqa: E402
                      QuantifiedSegment, match)

RESTRICTORS = ("WALK", "TRAIL", "ACYCLIC", "SIMPLE")
SELECTORS = ("ALL", "ANY", "ALL SHORTEST", "ANY SHORTEST")
COMBOS = [(r, s) for r in RESTRICTORS for s in SELECTORS]


def signature(g: PropertyGraph, anchor: str, lo: int, hi: int, restrictor, selector):
    """What an engine could observe: the answer, as the suite compares it.

    Deterministic selectors are compared as the exact multiset of endpoint pairs.
    Nondeterministic ones are compared as the specification the standard actually
    fixes -- the admissible set and the per-partition count -- because any answer
    inside that specification conforms, so two combinations with the same
    specification are indistinguishable however the engine chooses.
    """
    pat = PathPattern(
        start=NodePattern(labels=("N",), where=lambda n, _a=anchor: n.id == _a),
        segments=(QuantifiedSegment(EdgePattern(labels=("E",), direction="right"),
                                    NodePattern(labels=("N",)), lo, hi),),
        restrictor=restrictor, selector=selector)
    res = match(g, pat)
    if res.deterministic:
        return ("d", tuple(sorted(collections.Counter(
            (p.start, p.end) for p in res.exact).items())))
    return ("n",
            tuple(sorted(res.per_partition_count.items())),
            tuple(sorted((p.nodes, p.edges) for p in res.admissible)))


def graphs(max_nodes: int, max_edges: int):
    """Every directed multigraph up to the size limits, self-loops and parallel edges
    included. Edge multisets are enumerated as combinations with repetition, so two
    graphs that differ only by edge naming are generated once."""
    for n in range(2, max_nodes + 1):
        nodes = [chr(ord("a") + i) for i in range(n)]
        slots = [(u, v) for u in nodes for v in nodes]
        for m in range(1, max_edges + 1):
            for pick in itertools.combinations_with_replacement(slots, m):
                g = PropertyGraph()
                for x in nodes:
                    g.add_node(x, labels=("N",), name=x)
                for i, (u, v) in enumerate(pick):
                    g.add_edge(f"e{i}", u, v, labels=("E",))
                yield g, nodes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-nodes", type=int, default=4)
    ap.add_argument("--max-edges", type=int, default=5)
    ap.add_argument("--max-bound", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "separation.json"))
    args = ap.parse_args()

    pairs = list(itertools.combinations(range(len(COMBOS)), 2))
    witness: dict[tuple[int, int], dict] = {}
    n_graphs = n_probes = 0

    for g, nodes in graphs(args.max_nodes, args.max_edges):
        n_graphs += 1
        for anchor in nodes:
            for hi in range(2, args.max_bound + 1):
                sig = [signature(g, anchor, 1, hi, r, s) for r, s in COMBOS]
                n_probes += 1
                for i, j in pairs:
                    if (i, j) in witness:
                        continue
                    if sig[i] != sig[j]:
                        witness[(i, j)] = {
                            "edges": [[e.src, e.dst] for e in g.edges.values()],
                            "nodes": len(g.nodes), "anchor": anchor,
                            "quantifier": [1, hi],
                        }
        if len(witness) == len(pairs):
            break

    unobservable = [[COMBOS[i], COMBOS[j]] for i, j in pairs if (i, j) not in witness]
    out = {
        "sweep": {"max_nodes": args.max_nodes, "max_edges": args.max_edges,
                  "max_bound": args.max_bound,
                  "graphs_enumerated": n_graphs, "pattern_probes": n_probes},
        "combinations": len(COMBOS),
        "pairs": len(pairs),
        "separated": len(witness),
        "unobservable": unobservable,
        "observable_classes": None,
        "witnesses": {f"{COMBOS[i]}|{COMBOS[j]}": w for (i, j), w in
                      sorted(witness.items())},
    }
    # Collapse the combinations into equivalence classes under "no witness exists".
    parent = list(range(len(COMBOS)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in pairs:
        if (i, j) not in witness:
            parent[find(i)] = find(j)
    out["observable_classes"] = len({find(i) for i in range(len(COMBOS))})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    print(f"graphs enumerated : {n_graphs}")
    print(f"pattern probes    : {n_probes}")
    print(f"pairs separated   : {len(witness)}/{len(pairs)}")
    print(f"observable classes: {out['observable_classes']} of {len(COMBOS)} combinations")
    for a, b in unobservable:
        print(f"  no witness: {tuple(a)}  ==  {tuple(b)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
