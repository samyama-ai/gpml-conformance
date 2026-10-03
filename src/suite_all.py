"""The suite the runner executes: v1's hand-picked cases plus the v2 matrix, deduplicated.

v1's 17 ids are kept exactly as they were so the published v1 numbers stay addressable.
Where a v2 dimension regenerates a construct v1 already had -- same fixture, same
pattern, same query text -- the v1 case wins and the v2 id is recorded as an alias
rather than counted twice. Double-counting a construct would inflate every denominator
in the paper.
"""
from __future__ import annotations

from suite import CASES as V1_CASES
from suite_v2 import ALL_V2


def _key(c):
    """What makes two cases the same test: same graph, same question, same text."""
    segs = tuple((s.edge.labels, s.edge.direction, s.node.labels, s.lo, s.hi)
                 for s in c.ref.segments)
    return (c.fixture, c.ref.restrictor, c.ref.selector, segs,
            c.cypher, c.cypher_gql, c.cypher_qpp, c.pgq)


_seen: dict = {}
CASES = []
ALIASES: dict[str, str] = {}

for _c in list(V1_CASES) + list(ALL_V2):
    k = _key(_c)
    if k in _seen:
        ALIASES[_c.id] = _seen[k]
        continue
    _seen[k] = _c.id
    CASES.append(_c)

BY_ID = {c.id: c for c in CASES}

GROUPS: dict[str, list[str]] = {}
for _c in CASES:
    GROUPS.setdefault(_c.group, []).append(_c.id)

# A case with no clause is not a conformance test. Fail loudly at import rather than
# quietly publishing a row nobody can trace to a rule.
_no_clause = [c.id for c in CASES if not c.clause.strip()]
if _no_clause:
    raise AssertionError(f"cases with no clause: {_no_clause}")
