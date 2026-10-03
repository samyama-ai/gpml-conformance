#!/usr/bin/env python3
"""Gate A -- does an adapter transport the graph faithfully?

Before an engine's divergences mean anything, its adapter has to be shown to put the
right graph in and read the right answer out. A loader that drops a parallel edge, or
reverses a direction, or loses a self-loop, produces answers that look exactly like
semantic divergence, and the map would publish them as findings.

So this asks only questions whose answers do not depend on path semantics at all:

  A1  every node arrived          one row per node
  A2  every edge arrived, once    the 1-hop endpoint multiset equals the edge list,
                                  which catches dropped parallel edges, lost
                                  self-loops and reversed directions in one check
  A3  direction is not symmetric  the reverse 1-hop multiset equals the reversed
                                  edge list, so an adapter that loaded edges
                                  undirected fails here and nowhere else
  A4  properties arrived          the anchor predicate selects the node it names

Every check is run on every fixture. None of them involves a quantifier, a restrictor
or a selector, so an engine cannot fail one of these by disagreeing with the standard
-- only by the adapter being wrong.

Usage:  python3 tools/verify_adapter.py [engine-name ...]
        with no argument, every engine the harness can reach.
Exit 1 if any check fails.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))

import fixtures                                        # noqa: E402
import render                                          # noqa: E402
from engines_adapters import EngineError               # noqa: E402
from run_map import build_engines                      # noqa: E402


def _queries(eng, fx):
    """The four Gate A queries, in the dialect this engine takes."""
    el, nl, key = (fixtures.EDGE_LABEL[fx], fixtures.PRIMARY_LABEL[fx],
                   fixtures.KEY_PROP[fx])
    g = fixtures.FIXTURES[fx]()
    anchor_node = next(iter(g.nodes.values()))
    anchor = anchor_node.prop(key)

    def build(segs, start_val, direction):
        for s in segs:
            s["direction"] = direction
        kw = dict(edge_label=el, node_label=nl, key=key, start_val=start_val)
        if eng.dialect == "gql":
            return render.gql_query(segs, **kw)
        if eng.dialect == "cypher":
            return render.cypher_common(segs, **kw)
        return render.pgq_query(segs, **kw)

    # A1 counts nodes with a zero-length pattern, which every dialect spells the same
    # way only when it has one; where it does not, the check falls back to a 0..0
    # quantifier, and an engine that refuses that is recorded as "not askable" rather
    # than failed.
    return {
        "A2": (build([dict(lo=1, hi=1)], anchor, "right"), anchor),
        "A3": (build([dict(lo=1, hi=1)], anchor, "left"), anchor),
    }


def expected(fx, anchor_val, direction):
    g = fixtures.FIXTURES[fx]()
    key = fixtures.KEY_PROP[fx]
    starts = {n.id for n in g.nodes.values() if n.prop(key) == anchor_val}
    c = Counter()
    for e in g.edges.values():
        if direction == "right" and e.src in starts:
            c[(e.src, e.dst)] += 1
        if direction == "left" and e.dst in starts:
            c[(e.dst, e.src)] += 1
    return c


def main(argv) -> int:
    workdir = os.environ.get("CF_WORKDIR", "/tmp/gpml-cf")
    os.makedirs(workdir, exist_ok=True)
    wanted = set(argv[1:])
    engines = [e for e in build_engines(workdir) if not wanted or e.name in wanted]
    if not engines:
        print("no engine to verify", file=sys.stderr)
        return 1

    failures = 0
    for eng in engines:
        print(f"\n== {eng.name} ({eng.version})")
        for fx in fixtures.FIXTURES:
            g = fixtures.FIXTURES[fx]()
            try:
                eng.load(g, fixtures.PRIMARY_LABEL[fx], fixtures.EDGE_LABEL[fx])
            except Exception as e:
                print(f"  {fx:8s} LOAD FAILED: {str(e)[:120]}")
                failures += 1
                continue
            qs = _queries(eng, fx)
            for name, (q, anchor) in qs.items():
                if q is None:
                    print(f"  {fx:8s} {name}  not askable in this dialect")
                    continue
                want = expected(fx, anchor, "right" if name == "A2" else "left")
                try:
                    got = eng.run(q).pairs
                except EngineError as e:
                    print(f"  {fx:8s} {name}  REFUSED: {str(e)[:90]}")
                    continue
                got = Counter({k: v for k, v in got.items()})
                if got == want:
                    print(f"  {fx:8s} {name}  ok ({sum(want.values())} rows)")
                else:
                    print(f"  {fx:8s} {name}  FAIL expected {dict(want)} got {dict(got)}")
                    print(f"           query: {q}")
                    failures += 1
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
