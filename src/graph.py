"""Property-graph data model, following the GPML formalisation of
Deutsch et al., "Graph Pattern Matching in GQL and SQL/PGQ" (SIGMOD 2022), Sec. 2.

A property graph is (N, E, rho, lambda, pi):
  N, E        disjoint identifier sets for nodes and edges
  rho         maps an edge to an ordered pair (directed) or an unordered pair (undirected)
  lambda      maps an element to a *set* of labels (possibly empty)
  pi          partial map from (element, property name) to a value
Two distinct edges may connect the same pair of nodes; self-loops are allowed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Node:
    id: str
    labels: frozenset[str] = frozenset()
    props: tuple[tuple[str, Any], ...] = ()

    def prop(self, k: str):
        return dict(self.props).get(k)


@dataclass(frozen=True)
class Edge:
    id: str
    src: str
    dst: str
    labels: frozenset[str] = frozenset()
    props: tuple[tuple[str, Any], ...] = ()
    undirected: bool = False

    def prop(self, k: str):
        return dict(self.props).get(k)

    def endpoints(self) -> tuple[str, str]:
        return (self.src, self.dst)


@dataclass
class PropertyGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)

    def add_node(self, id: str, labels=(), **props) -> Node:
        n = Node(id, frozenset(labels), tuple(sorted(props.items())))
        self.nodes[id] = n
        return n

    def add_edge(self, id: str, src: str, dst: str, labels=(), undirected=False, **props) -> Edge:
        if src not in self.nodes or dst not in self.nodes:
            raise KeyError(f"edge {id}: endpoint not in graph")
        e = Edge(id, src, dst, frozenset(labels), tuple(sorted(props.items())), undirected)
        self.edges[id] = e
        return e

    def incident(self, node_id: str, direction: str) -> list[tuple[Edge, str]]:
        """Edges usable to leave `node_id`, with the node reached.

        direction is one of:
          'right'  the pattern is -[]->  : traverse a directed edge forward only
          'left'   the pattern is <-[]-  : traverse a directed edge backward only
          'any'    the pattern is -[]-   : traverse in either direction
        An undirected edge is traversable in either direction under any of the three
        (GPML Sec. 2: an undirected edge "connects" its endpoints, without orientation).
        """
        out: list[tuple[Edge, str]] = []
        seen: set[tuple[str, str]] = set()

        def push(e: "Edge", to: str) -> None:
            # A path is an alternating sequence of nodes and edges; traversal
            # orientation is not part of the sequence. For a self-loop the two
            # orientations yield the *same* path, so they are one binding.
            if (e.id, to) in seen:
                return
            seen.add((e.id, to))
            out.append((e, to))

        for e in self.edges.values():
            if e.undirected:
                if e.src == node_id:
                    push(e, e.dst)
                if e.dst == node_id:
                    push(e, e.src)
                continue
            if direction in ("right", "any") and e.src == node_id:
                push(e, e.dst)
            if direction in ("left", "any") and e.dst == node_id:
                push(e, e.src)
        return out
