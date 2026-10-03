#!/usr/bin/env python3
"""Pick the fixture beds the G1 grid runs on, by search rather than by taste.

A grid cell can only catch an engine if its reference answer differs from the other
cells'. So the bed -- (fixture, anchor node, quantifier bound) -- is chosen to maximise
the number of cell pairs it separates, ties broken by the smallest total answer size,
because a reproducer has to stay checkable by eye.

The rule is mechanical and runs before any engine does, so the beds are not chosen to
flatter or to embarrass anybody. Re-run to re-derive what src/suite_v2.py hardcodes.
"""
from __future__ import annotations

import collections
import itertools
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))

import fixtures                                            # noqa: E402
from gpml_ref import (EdgePattern, NodePattern, PathPattern,  # noqa: E402
                      QuantifiedSegment, match)

RESTRICTORS = ("WALK", "TRAIL", "ACYCLIC", "SIMPLE")
SELECTORS = ("ALL", "ANY", "ALL SHORTEST", "ANY SHORTEST")


def signatures(fx: str, anchor: str, lo: int, hi: int):
    g = fixtures.FIXTURES[fx]()
    key, nl, el = (fixtures.KEY_PROP[fx], fixtures.PRIMARY_LABEL[fx],
                   fixtures.EDGE_LABEL[fx])
    out = []
    for r in RESTRICTORS:
        for s in SELECTORS:
            pat = PathPattern(
                start=NodePattern(labels=(nl,),
                                  where=lambda n, _k=key, _v=anchor: n.prop(_k) == _v),
                segments=(QuantifiedSegment(EdgePattern(labels=(el,), direction="right"),
                                            NodePattern(labels=(nl,)), lo, hi),),
                restrictor=r, selector=s)
            res = match(g, pat)
            if res.deterministic:
                out.append(("d", tuple(sorted(collections.Counter(
                    (p.start, p.end) for p in res.exact).items()))))
            else:
                out.append(("n", tuple(sorted(res.per_partition_count.items())),
                            tuple(sorted((p.nodes, p.edges) for p in res.admissible))))
    return out


def score(fx, anchor, lo, hi):
    sg = signatures(fx, anchor, lo, hi)
    sep = sum(1 for a, b in itertools.combinations(sg, 2) if a != b)
    rows = sum(sum(v for _, v in s[1]) for s in sg)
    return sep, len(set(sg)), rows


def main() -> int:
    rows = []
    for fx in fixtures.FIXTURES:
        g = fixtures.FIXTURES[fx]()
        key = fixtures.KEY_PROP[fx]
        for anchor in sorted({n.prop(key) for n in g.nodes.values()}):
            for hi in range(2, 7):
                sep, distinct, nrows = score(fx, anchor, 1, hi)
                rows.append((sep, -nrows, distinct, fx, anchor, hi))
    rows.sort(reverse=True)
    print(f"{'sep/120':>8} {'classes':>8} {'rows':>6}  bed")
    for sep, negrows, distinct, fx, anchor, hi in rows[:12]:
        print(f"{sep:8d} {distinct:8d} {-negrows:6d}  {fx} anchor={anchor!r} {{1,{hi}}}")
    best_by_fixture = {}
    for sep, negrows, distinct, fx, anchor, hi in rows:
        best_by_fixture.setdefault(fx, (sep, -negrows, distinct, anchor, hi))
    print("\nbest bed per fixture:")
    for fx, (sep, nrows, distinct, anchor, hi) in sorted(
            best_by_fixture.items(), key=lambda kv: (-kv[1][0], kv[1][1])):
        print(f"  {fx:8s} anchor={anchor!r:10s} {{1,{hi}}}  sep={sep}/120 "
              f"classes={distinct} rows={nrows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
