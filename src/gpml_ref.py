"""An executable reference semantics for the path-pattern core of GPML.

GPML is the graph pattern matching language shared by GQL (ISO/IEC 39075:2024) and
SQL/PGQ (ISO/IEC 9075-16:2023). This module implements, literally and without
optimisation, the definitions given in the standard's reference exposition:

  A. Deutsch, N. Francis, A. Green, K. Hare, B. Li, L. Libkin, T. Lindaaker,
  V. Marsault, W. Martens, J. Michels, F. Murlak, S. Plantikow, P. Selmer,
  O. van Rest, H. Voigt, D. Vrgoc, M. Wu, F. Zemke.
  "Graph Pattern Matching in GQL and SQL/PGQ". SIGMOD 2022. arXiv:2112.06217.

The definitions implemented here, with the clause each comes from:

  Sec. 2   A *path* is an alternating sequence of nodes and edges that starts and
           ends with a node, consecutive nodes being connected by the edge between
           them. What graph theory calls a walk. Orientation is not stored.

  Fig. 7   Restrictors.  TRAIL    - no repeated edges.
                         ACYCLIC  - no repeated nodes.
                         SIMPLE   - no repeated nodes, except that the first and
                                    last nodes may be the same.
           With no restrictor the matched object is an unrestricted path, i.e. a
           WALK: repeated nodes *and* repeated edges are permitted.

  Fig. 8   Selectors.    ALL, ANY, ALL SHORTEST, ANY SHORTEST. A selector
           "conceptually partitions the solution space on the endpoints and selects
           a finite set of matches from each partition" (Sec. 5.1).

  Sec. 5.1 "if combined, selectors are always applied after restrictors."

  Sec. 5   "Every unbounded quantifier must be contained in the scope of either a
           restrictor or a selector or both." A *bounded* quantifier needs neither:
           the paper's own example (Sec. 5.1, end) has a bounded pattern
           `->{1,10} ... ->{1,10}` with no restrictor whose solution
           path(a5,t8,a1,t1,a3,t7,a5,t8,a1) repeats the edge t8. Under WALK that
           is a solution; under TRAIL, SIMPLE or ACYCLIC it is not.

Nothing in this module consults any database engine. That is the point: it is the
yardstick engines are measured against, so it must not be derived from one.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from graph import Edge, Node, PropertyGraph

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Path:
    """An alternating sequence n0, e1, n1, ..., ek, nk, held as two tuples."""

    nodes: tuple[str, ...]
    edges: tuple[str, ...]

    def __post_init__(self):
        if len(self.nodes) != len(self.edges) + 1:
            raise ValueError("a path of k edges must have k+1 nodes")

    @property
    def length(self) -> int:
        return len(self.edges)

    @property
    def start(self) -> str:
        return self.nodes[0]

    @property
    def end(self) -> str:
        return self.nodes[-1]

    def extend(self, edge_id: str, node_id: str) -> "Path":
        return Path(self.nodes + (node_id,), self.edges + (edge_id,))

    def render(self) -> str:
        """The paper's notation: path(a6,t5,a3,t2,a2)."""
        parts: list[str] = []
        for i, n in enumerate(self.nodes):
            parts.append(n)
            if i < len(self.edges):
                parts.append(self.edges[i])
        return "path(" + ",".join(parts) + ")"


# --------------------------------------------------------------------------
# Restrictors (Fig. 7)
# --------------------------------------------------------------------------

RESTRICTORS = ("WALK", "TRAIL", "ACYCLIC", "SIMPLE")


def satisfies_restrictor(p: Path, restrictor: str) -> bool:
    if restrictor == "WALK":
        return True
    if restrictor == "TRAIL":
        return len(set(p.edges)) == len(p.edges)
    if restrictor == "ACYCLIC":
        return len(set(p.nodes)) == len(p.nodes)
    if restrictor == "SIMPLE":
        # no repeated nodes, except that the first and last may be the same
        if p.length == 0:
            return True
        if p.nodes[0] == p.nodes[-1]:
            interior = p.nodes[:-1]
            return len(set(interior)) == len(interior)
        return len(set(p.nodes)) == len(p.nodes)
    raise ValueError(f"unknown restrictor {restrictor!r}")


def prefix_can_still_satisfy(p: Path, restrictor: str) -> bool:
    """Monotone prunability of a restrictor over path prefixes.

    TRAIL and ACYCLIC are prefix-closed: a prefix that already repeats an edge
    (resp. a node) can never become a trail (resp. acyclic path). SIMPLE is not
    prefix-closed in the same way -- a prefix with first == last is fine only if
    the path stops there -- so SIMPLE prunes on the weaker interior condition.
    """
    if restrictor == "WALK":
        return True
    if restrictor == "TRAIL":
        return len(set(p.edges)) == len(p.edges)
    if restrictor == "ACYCLIC":
        return len(set(p.nodes)) == len(p.nodes)
    if restrictor == "SIMPLE":
        interior = p.nodes[:-1] if p.length > 0 else p.nodes
        return len(set(interior)) == len(interior)
    raise ValueError(f"unknown restrictor {restrictor!r}")


# --------------------------------------------------------------------------
# Selectors (Fig. 8, Sec. 5.1)
# --------------------------------------------------------------------------

SELECTORS = ("ALL", "ANY", "ALL SHORTEST", "ANY SHORTEST")


def apply_selector(paths: list[Path], selector: str) -> "SelectorResult":
    """Partition on endpoints, then select within each partition.

    ANY and ANY SHORTEST are *nondeterministic*: the standard fixes the size of
    the answer (one path per partition) but not which path. So this returns a
    specification -- the exact multiset when deterministic, and otherwise a
    per-partition cardinality plus the set of admissible paths -- rather than
    pretending there is a single right answer.
    """
    if selector not in SELECTORS:
        raise ValueError(f"unknown selector {selector!r}")

    partitions: dict[tuple[str, str], list[Path]] = {}
    for p in paths:
        partitions.setdefault((p.start, p.end), []).append(p)

    if selector == "ALL":
        return SelectorResult(deterministic=True, exact=list(paths), admissible=set(paths),
                              per_partition_count={k: len(v) for k, v in partitions.items()})

    if selector == "ANY":
        return SelectorResult(deterministic=False, exact=None,
                              admissible=set(paths),
                              per_partition_count={k: 1 for k in partitions})

    shortest: dict[tuple[str, str], list[Path]] = {}
    for k, v in partitions.items():
        m = min(p.length for p in v)
        shortest[k] = [p for p in v if p.length == m]

    if selector == "ALL SHORTEST":
        exact = [p for k in partitions for p in shortest[k]]
        return SelectorResult(deterministic=True, exact=exact,
                              admissible={p for v in shortest.values() for p in v},
                              per_partition_count={k: len(v) for k, v in shortest.items()})

    # ANY SHORTEST
    return SelectorResult(deterministic=False, exact=None,
                          admissible={p for v in shortest.values() for p in v},
                          per_partition_count={k: 1 for k in shortest})


@dataclass
class SelectorResult:
    deterministic: bool
    exact: Optional[list[Path]]
    admissible: set[Path]
    per_partition_count: dict[tuple[str, str], int]

    def accepts(self, observed: list[Path]) -> tuple[bool, str]:
        """Does an engine's answer conform to this specification?"""
        if self.deterministic:
            assert self.exact is not None
            if sorted(map(_key, observed)) == sorted(map(_key, self.exact)):
                return True, ""
            return False, (f"expected multiset of {len(self.exact)} path(s), "
                           f"observed {len(observed)}")
        counts: dict[tuple[str, str], int] = {}
        for p in observed:
            if p not in self.admissible:
                return False, f"{p.render()} is not an admissible selection"
            counts[(p.start, p.end)] = counts.get((p.start, p.end), 0) + 1
        if counts != self.per_partition_count:
            return False, f"per-endpoint-pair counts {counts} != {self.per_partition_count}"
        return True, ""


def _key(p: Path):
    return (p.nodes, p.edges)


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NodePattern:
    var: Optional[str] = None
    labels: tuple[str, ...] = ()
    where: Optional[Callable[[Node], bool]] = None

    def matches(self, n: Node) -> bool:
        if self.labels and not set(self.labels) <= n.labels:
            return False
        return self.where(n) if self.where else True


@dataclass(frozen=True)
class EdgePattern:
    var: Optional[str] = None
    labels: tuple[str, ...] = ()
    direction: str = "right"          # 'right' | 'left' | 'any'
    where: Optional[Callable[[Edge], bool]] = None

    def matches(self, e: Edge) -> bool:
        if self.labels and not set(self.labels) & set(e.labels):
            return False
        return self.where(e) if self.where else True


UNBOUNDED = -1


@dataclass(frozen=True)
class QuantifiedSegment:
    """`(node)-[edge]->{lo,hi}` : the edge-and-node step repeated lo..hi times.

    hi == UNBOUNDED encodes the standard's `*` (lo 0) and `+` (lo 1).
    """

    edge: EdgePattern
    node: NodePattern
    lo: int
    hi: int


def resolve_bound(graph: PropertyGraph, hi: int, restrictor: str, selector: str) -> int:
    """A finite enumeration bound for an unbounded quantifier.

    Sec. 5: an unbounded quantifier must lie in the scope of a restrictor or a
    selector. Each case gives a sound finite bound on the paths that can survive:

      TRAIL             at most |E| edges, since no edge repeats
      ACYCLIC, SIMPLE   at most |N| edges (|N|-1, plus one to close a simple cycle)
      WALK + SHORTEST   a shortest walk between two nodes is a simple path, so at
                        most |N|-1 edges; longer walks cannot be selected
      WALK + ALL/ANY    unbounded and *not* finitely specifiable. ALL is rejected
                        by the standard itself; ANY is admitted by the standard
                        but its admissible set is infinite, so no finite oracle
                        exists. Out of scope -- raised, never guessed.
    """
    if hi != UNBOUNDED:
        return hi
    if restrictor == "TRAIL":
        return len(graph.edges)
    if restrictor in ("ACYCLIC", "SIMPLE"):
        return len(graph.nodes)
    if "SHORTEST" in selector:
        return max(len(graph.nodes) - 1, 0)
    raise ValueError(
        "unbounded quantifier under WALK with a non-shortest selector has no "
        "finite reference answer; the standard forbids the ALL case outright"
    )


@dataclass(frozen=True)
class PathPattern:
    """start node, then a sequence of quantified segments."""

    start: NodePattern
    segments: tuple[QuantifiedSegment, ...]
    restrictor: str = "WALK"
    selector: str = "ALL"


def match(graph: PropertyGraph, pat: PathPattern) -> SelectorResult:
    """Evaluate a path pattern: enumerate paths, filter by restrictor, then select.

    Order matters and is fixed by the standard (Sec. 5.1): "selectors are always
    applied after restrictors".
    """
    starts = [n.id for n in graph.nodes.values() if pat.start.matches(n)]
    frontier = [Path((s,), ()) for s in starts]

    for seg in pat.segments:
        hi = resolve_bound(graph, seg.hi, pat.restrictor, pat.selector)
        frontier = _expand_segment(graph, frontier, seg, pat.restrictor, hi)

    kept = [p for p in frontier if satisfies_restrictor(p, pat.restrictor)]
    return apply_selector(kept, pat.selector)


def _expand_segment(graph: PropertyGraph, frontier: list[Path],
                    seg: QuantifiedSegment, restrictor: str, hi: int) -> list[Path]:
    """Repeat the *edge* step lo..hi times, then require the segment's node pattern.

    The quantifier binds the edge pattern, not the node pattern: in the standard's
    own example `(p WHERE p.owner='Natalia')->{1,10}(q WHERE q.owner='Mike')`, the
    printed solution path(a5,t8,a1,t1,a3,...) passes *through* a1 (Scott) on its way
    to a3 (Mike). Intermediate nodes are therefore unconstrained; only the node at
    the end of the repetition must satisfy the segment's node pattern.
    """
    out: list[Path] = []
    for base in frontier:
        current = [base]
        if seg.lo == 0 and seg.node.matches(graph.nodes[base.end]):
            out.append(base)
        for rep in range(1, hi + 1):
            nxt: list[Path] = []
            for p in current:
                for e, to in graph.incident(p.end, seg.edge.direction):
                    if not seg.edge.matches(e):
                        continue
                    q = p.extend(e.id, to)
                    if not prefix_can_still_satisfy(q, restrictor):
                        continue
                    nxt.append(q)
            current = nxt
            if rep >= seg.lo:
                out.extend(q for q in current if seg.node.matches(graph.nodes[q.end]))
            if not current:
                break
    return out
