"""The conformance suite: one case per construct, with the reference pattern and
the surface syntax for each dialect.

Every case carries:
  ref      the abstract GPML pattern, evaluated by src/gpml_ref.py -- the yardstick
  cypher   the query for openCypher-family engines (Neo4j, Memgraph, Kuzu, AGE, Samyama)
  pgq      the query for SQL/PGQ engines (DuckPGQ)
Both surface forms must be the *natural* way to write the pattern in that dialect.
Where a dialect has no way to express the construct the entry is None, and the cell is
scored INEXPRESSIBLE, not as a failure.

Comparison level L1 is the multiset of (start_id, end_id) pairs. Every engine can
produce it, so the map is computed at L1. Level L2, the multiset of edge-id sequences,
is a refinement recorded where the engine can return path bindings.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from gpml_ref import (EdgePattern, NodePattern, PathPattern, QuantifiedSegment,
                      UNBOUNDED)

ANY_NODE = NodePattern(labels=("N",))
E = lambda d="right": EdgePattern(labels=("E",), direction=d)


def start_named(name: str) -> NodePattern:
    return NodePattern(labels=("N",), where=lambda n, _v=name: n.prop("name") == _v)


def seg(lo, hi, direction="right", node=ANY_NODE):
    return QuantifiedSegment(E(direction), node, lo, hi)


@dataclass(frozen=True)
class Case:
    id: str
    construct: str
    fixture: str
    ref: PathPattern
    cypher: Optional[str]
    pgq: Optional[str]
    note: str
    # Where the Cypher rendering has to spell out a numeric bound because
    # openCypher has no restrictor keyword, this is that bound. It is used only to
    # build the "engine's own declared semantics" reference, so the two forms stay
    # comparable.
    cypher_bound: Optional[int] = None
    # A rendering for engines whose dialect is openCypher *plus* the GQL restrictor
    # and selector prefixes. When this work started no engine had them, so every such
    # cell scored INEXPRESSIBLE. Samyama-Graph gained them in response to this suite
    # (samyama-ai/samyama-graph#1141), so those cells can now be measured rather than
    # excused. Engines that declare support get this text; the rest still get `cypher`.
    cypher_gql: Optional[str] = None


def _p(start, segs, restrictor="WALK", selector="ALL"):
    return PathPattern(start=start, segments=tuple(segs),
                       restrictor=restrictor, selector=selector)


CASES: list[Case] = [

    # ---- path modes on a bounded quantifier -------------------------------
    Case(
        id="mode-walk-bounded",
        construct="path mode: none given (WALK) on a bounded quantifier",
        fixture="cycle2",
        ref=_p(start_named("m"), [seg(1, 4)], "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*1..4]->(y:N) WHERE x.name='m' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{1,4}(y:N) WHERE x.name='m' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="With no restrictor the standard's matched object is an unrestricted "
             "path, i.e. a walk (Fig. 7 lists only TRAIL/ACYCLIC/SIMPLE as "
             "restrictions; Sec. 5.1's {1,10} example returns an edge-repeating path).",
    ),
    Case(
        id="mode-trail-bounded",
        construct="path mode: TRAIL on a bounded quantifier",
        fixture="cycle2",
        ref=_p(start_named("m"), [seg(1, 4)], "TRAIL", "ALL"),
        cypher="MATCH p=(x:N)-[:E*1..4]->(y:N) WHERE x.name='m' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH TRAIL (x:N)-[e:E]->{1,4}(y:N) WHERE x.name='m' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="openCypher has no TRAIL keyword; its variable-length pattern is "
             "specified to use relationship uniqueness, which is TRAIL. So the "
             "Cypher text is the same as mode-walk-bounded on purpose: the pair of "
             "cases asks which of the two meanings that one query has.",
    ),
    Case(
        id="mode-acyclic-bounded",
        construct="path mode: ACYCLIC on a bounded quantifier",
        fixture="micro",
        ref=_p(start_named("a"), [seg(1, 3)], "ACYCLIC", "ALL"),
        cypher=None,
        cypher_gql="MATCH ACYCLIC (x:N)-[:E*1..3]->(y:N) WHERE x.name='a' RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH ACYCLIC (x:N)-[e:E]->{1,3}(y:N) WHERE x.name='a' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="No openCypher surface syntax.",
    ),
    Case(
        id="mode-simple-bounded",
        construct="path mode: SIMPLE on a bounded quantifier",
        fixture="micro",
        ref=_p(start_named("a"), [seg(1, 3)], "SIMPLE", "ALL"),
        cypher=None,
        cypher_gql="MATCH SIMPLE (x:N)-[:E*1..3]->(y:N) WHERE x.name='a' RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH SIMPLE (x:N)-[e:E]->{1,3}(y:N) WHERE x.name='a' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="SIMPLE differs from ACYCLIC only when the path closes a cycle; on "
             "micro the length-3 path a->b->c->a is SIMPLE but not ACYCLIC.",
    ),

    # ---- the walk/trail question in its sharpest form ---------------------
    Case(
        id="walk-revisits-same-edge",
        construct="WALK may traverse one edge twice (any-direction, length 2)",
        fixture="single",
        ref=_p(start_named("u"), [seg(2, 2, "any")], "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*2..2]-(y:N) WHERE x.name='u' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]-{2,2}(y:N) WHERE x.name='u' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="One edge u-e1-v. The only length-2 any-direction walk from u is "
             "u,e1,v,e1,u. Under WALK it is a match; under TRAIL it is not. This is "
             "the cleanest single discriminator between the two readings.",
    ),

    # ---- quantifier bounds -------------------------------------------------
    Case(
        id="quant-zero-lower-bound",
        construct="quantifier {0,2}: is the zero-length path a match?",
        fixture="micro",
        ref=_p(start_named("a"), [seg(0, 2)], "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*0..2]->(y:N) WHERE x.name='a' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{0,2}(y:N) WHERE x.name='a' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="A zero-repetition match leaves the path at its start node, so (a,a) "
             "must appear.",
    ),
    Case(
        id="quant-zero-zero",
        construct="quantifier {0,0}: exactly the zero-length path",
        fixture="micro",
        ref=_p(start_named("a"), [seg(0, 0)], "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*0..0]->(y:N) WHERE x.name='a' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{0,0}(y:N) WHERE x.name='a' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="The degenerate case. Exactly one answer, (a,a).",
    ),

    # ---- parallel edges and self-loops -------------------------------------
    Case(
        id="parallel-edges",
        construct="two distinct edges between the same pair are two matches",
        fixture="micro",
        ref=_p(start_named("a"), [seg(1, 1)], "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*1..1]->(y:N) WHERE x.name='a' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{1,1}(y:N) WHERE x.name='a' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="Sec. 2: 'the definition does not preclude having two different edges "
             "connecting the same nodes'. Answer is the multiset {(a,b),(a,b)}.",
    ),
    Case(
        id="self-loop-trail",
        construct="a self-loop under TRAIL",
        fixture="loop",
        ref=_p(start_named("x"), [seg(1, 2)], "TRAIL", "ALL"),
        cypher="MATCH p=(u:N)-[:E*1..2]->(v:N) WHERE u.name='x' "
               "RETURN u.eid AS s, v.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH TRAIL (u:N)-[e:E]->{1,2}(v:N) WHERE u.name='x' "
            "COLUMNS (u.eid AS s, v.eid AS t)) SELECT s, t",
        note="A self-loop repeats a node but not an edge, so it is a trail and not "
             "acyclic. Separates the two restrictors.",
    ),
    Case(
        id="self-loop-acyclic",
        construct="a self-loop under ACYCLIC",
        fixture="loop",
        ref=_p(start_named("x"), [seg(1, 2)], "ACYCLIC", "ALL"),
        cypher=None,
        cypher_gql="MATCH ACYCLIC (u:N)-[:E*1..2]->(v:N) WHERE u.name='x' RETURN u.eid AS s, v.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH ACYCLIC (u:N)-[e:E]->{1,2}(v:N) WHERE u.name='x' "
            "COLUMNS (u.eid AS s, v.eid AS t)) SELECT s, t",
        note="",
    ),

    # ---- direction ---------------------------------------------------------
    Case(
        id="direction-any",
        construct="an any-direction edge pattern traverses directed edges backwards",
        fixture="micro",
        ref=_p(start_named("b"), [seg(1, 1, "any")], "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*1..1]-(y:N) WHERE x.name='b' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]-{1,1}(y:N) WHERE x.name='b' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="From b: forward to c, and backwards along both parallel edges to a.",
    ),
    Case(
        id="direction-left",
        construct="a right-to-left edge pattern",
        fixture="micro",
        ref=_p(start_named("b"), [seg(1, 1, "left")], "WALK", "ALL"),
        cypher="MATCH p=(x:N)<-[:E*1..1]-(y:N) WHERE x.name='b' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)<-[e:E]-{1,1}(y:N) WHERE x.name='b' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="",
    ),

    # ---- binding of the node pattern under a quantifier --------------------
    Case(
        id="interior-node-unconstrained",
        construct="the node pattern binds at the segment end, not at interior nodes",
        fixture="tagged",
        ref=_p(start_named("p"), [seg(2, 2, node=NodePattern(labels=("N", "Mark")))],
               "WALK", "ALL"),
        cypher="MATCH p=(x:N)-[:E*2..2]->(y:N:Mark) WHERE x.name='p' "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{2,2}(y:N&Mark) WHERE x.name='p' "
            "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="The interior node q lacks :Mark. Sec. 5.1's own {1,10} example passes "
             "through a node that does not satisfy the segment's node pattern, so "
             "(p,r) must be returned. An engine that constrains interiors returns "
             "nothing.",
    ),

    # ---- selectors ---------------------------------------------------------
    Case(
        id="selector-all-shortest",
        construct="ALL SHORTEST partitions on endpoints",
        fixture="micro",
        ref=_p(start_named("a"), [seg(1, 3)], "WALK", "ALL SHORTEST"),
        cypher="MATCH p=(x:N)-[:E*1..3]->(y:N) WHERE x.name='a' "
               "WITH x, y, min(length(p)) AS m "
               "MATCH q=(x)-[:E*1..3]->(y) WHERE length(q)=m "
               "RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH ALL SHORTEST (x:N)-[e:E]->{1,3}(y:N) "
            "WHERE x.name='a' COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="'ALL SHORTEST keeps all paths having the same shortest length within "
             "each partition defined by a pair of endpoints' (Sec. 5.1). Two "
             "parallel edges a->b means two shortest paths in that partition.",
    ),
    Case(
        id="selector-any-shortest",
        construct="ANY SHORTEST returns exactly one path per endpoint pair",
        fixture="micro",
        ref=_p(start_named("a"), [seg(1, 3)], "WALK", "ANY SHORTEST"),
        cypher=None,
        cypher_gql="MATCH ANY SHORTEST (x:N)-[:E*1..3]->(y:N) WHERE x.name='a' RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH ANY SHORTEST (x:N)-[e:E]->{1,3}(y:N) "
            "WHERE x.name='a' COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="Nondeterministic in which path, deterministic in how many. Scored "
             "against the admissible set and the per-partition count, never against "
             "one chosen path.",
    ),
    Case(
        id="selector-any",
        construct="ANY returns exactly one path per endpoint pair, not necessarily short",
        fixture="micro",
        ref=_p(start_named("a"), [seg(1, 3)], "WALK", "ANY"),
        cypher=None,
        cypher_gql="MATCH ANY (x:N)-[:E*1..3]->(y:N) WHERE x.name='a' RETURN x.eid AS s, y.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH ANY (x:N)-[e:E]->{1,3}(y:N) "
            "WHERE x.name='a' COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t",
        note="",
    ),

    # ---- the standard's own worked examples --------------------------------
    Case(
        id="paper-trail-unbounded",
        construct="TRAIL with an unbounded quantifier (the standard's worked example)",
        fixture="fig1",
        ref=PathPattern(
            start=NodePattern(labels=("Account",),
                              where=lambda n: n.prop("owner") == "Dave"),
            segments=(QuantifiedSegment(
                EdgePattern(labels=("Transfer",), direction="right"),
                NodePattern(labels=("Account",),
                            where=lambda n: n.prop("owner") == "Aretha"),
                0, UNBOUNDED),),
            restrictor="TRAIL", selector="ALL"),
        cypher="MATCH p=(a:Account)-[:Transfer*0..8]->(b:Account) "
               "WHERE a.owner='Dave' AND b.owner='Aretha' "
               "RETURN a.eid AS s, b.eid AS t",
        pgq="FROM GRAPH_TABLE(g MATCH TRAIL (a:Account)-[e:Transfer]->*(b:Account) "
            "WHERE a.owner='Dave' AND b.owner='Aretha' "
            "COLUMNS (a.eid AS s, b.eid AS t)) SELECT s, t",
        note="Three bindings, printed in Sec. 5.1. The Cypher rendering bounds the "
             "quantifier at 8 (= |E|), which is exactly the trail bound, so the two "
             "forms ask the same question.",
        cypher_bound=8,
    ),
]

BY_ID = {c.id: c for c in CASES}
