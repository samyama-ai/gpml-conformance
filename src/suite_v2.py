"""The v2 construct matrix: cases generated from declared dimensions.

v1 hand-picked 17 constructs. Each is defensible and the set is not -- a reader cannot
tell what was left out. Here every case is produced by enumerating a dimension, so the
matrix states its own coverage, and the gaps are the ones written down in
docs/MATRIX-v2.md rather than the ones nobody noticed.

Groups (see docs/MATRIX-v2.md):
  G1  restrictor x selector, all 16, on two fixtures
  G2  quantifier form x restrictor
  G3  pattern shape x restrictor
  G4  patterns the standard requires to be rejected, with accept controls

Nothing here consults an engine, and no case is included whose reference answer the
oracle cannot compute: a construct with no reference answer is not a conformance test.
"""
from __future__ import annotations

import fixtures
import render
from gpml_ref import (UNBOUNDED, EdgePattern, NodePattern, PathPattern,
                      QuantifiedSegment)
from suite import Case

RESTRICTORS = ("WALK", "TRAIL", "ACYCLIC", "SIMPLE")
SELECTORS = ("ALL", "ANY", "ALL SHORTEST", "ANY SHORTEST")

# (fixture, anchor node value, quantifier) for the G1 grid. Two fixtures, because one
# graph that separates every pair at once stops being hand-checkable, and a reproducer
# nobody can check by eye is not a reproducer.
# Derived by tools/choose_beds.py, not chosen by taste: maximum separated cell pairs,
# ties broken by the smallest total answer size so a reproducer stays checkable by eye.
# fig1/Scott/{1,5} attains 114 of 120, which is the maximum any graph can attain --
# tools/separation.py shows the other 6 pairs have no separating witness at all.
# loop/x/{1,2} attains 112 of 120 in 34 answer rows, a third of fig1's size.
G1_BEDS = (
    ("fig1", "Scott", (1, 5)),
    ("loop", "x", (1, 2)),
)

CLAUSE_RESTRICTOR = "Deutsch et al. Fig. 7 (restrictors)"
CLAUSE_SELECTOR = "Deutsch et al. Fig. 8 and Sec. 5.1 (selectors, applied after restrictors)"
CLAUSE_QUANT = "Deutsch et al. Sec. 5 (quantified path patterns)"
CLAUSE_UNBOUNDED = ("Deutsch et al. Sec. 5: every unbounded quantifier must be "
                    "contained in the scope of a restrictor or a selector")
CLAUSE_INTERIOR = ("Deutsch et al. Sec. 5.1 worked example: the quantifier binds the "
                   "edge step, so intermediate nodes are unconstrained")


def _meta(fixture: str):
    return (fixtures.EDGE_LABEL[fixture], fixtures.PRIMARY_LABEL[fixture],
            fixtures.KEY_PROP[fixture])


def _start(fixture: str, value: str) -> NodePattern:
    key = fixtures.KEY_PROP[fixture]
    return NodePattern(labels=(fixtures.PRIMARY_LABEL[fixture],),
                       where=lambda n, _k=key, _v=value: n.prop(_k) == _v)


def _node(fixture: str) -> NodePattern:
    return NodePattern(labels=(fixtures.PRIMARY_LABEL[fixture],))


def _seg(fixture, lo, hi, direction="right", end_label=None, edge_where=None):
    node = (NodePattern(labels=(end_label,)) if end_label else _node(fixture))
    return QuantifiedSegment(
        EdgePattern(labels=(fixtures.EDGE_LABEL[fixture],), direction=direction,
                    where=edge_where),
        node, lo, hi)


def _unbounded_bound(fixture: str, restrictor: str) -> int:
    """The finite bound a dialect without `*` must be given, from the restrictor."""
    g = fixtures.FIXTURES[fixture]()
    return len(g.edges) if restrictor == "TRAIL" else len(g.nodes)


# ---------------------------------------------------------------------------
# G1 -- the restrictor x selector grid
# ---------------------------------------------------------------------------

def g1() -> list[Case]:
    out: list[Case] = []
    for fixture, anchor, (lo, hi) in G1_BEDS:
        edge_label, node_label, key = _meta(fixture)
        segs = [dict(lo=lo, hi=hi, direction="right")]
        kw = dict(edge_label=edge_label, node_label=node_label, key=key,
                  start_val=anchor)
        for restrictor in RESTRICTORS:
            for selector in SELECTORS:
                out.append(Case(
                    id=f"g1-{fixture}-{restrictor.lower()}-"
                       f"{selector.lower().replace(' ', '-')}",
                    construct=f"{restrictor} x {selector} on {{{lo},{hi}}} ({fixture})",
                    fixture=fixture,
                    ref=PathPattern(start=_start(fixture, anchor),
                                    segments=(_seg(fixture, lo, hi),),
                                    restrictor=restrictor, selector=selector),
                    cypher=render.cypher_common(segs, restrictor=restrictor,
                                                selector=selector, **kw),
                    cypher_gql=render.cypher_query(segs, restrictor=restrictor,
                                                   selector=selector, **kw),
                    cypher_qpp=render.cypher_query(segs, restrictor=restrictor,
                                                   selector=selector,
                                                   spelling="qpp", **kw),
                    pgq=render.pgq_query(segs, restrictor=restrictor,
                                         selector=selector, **kw),
                    gql=render.gql_query(segs, restrictor=restrictor,
                                         selector=selector, **kw),
                    group="G1",
                    clause=f"{CLAUSE_RESTRICTOR}; {CLAUSE_SELECTOR}",
                    note=f"G1 cell ({restrictor}, {selector}) on the {fixture} bed.",
                ))
    return out


# ---------------------------------------------------------------------------
# G2 -- quantifier forms
# ---------------------------------------------------------------------------

G2_FORMS = (
    ("none", None, None),
    ("0-0", 0, 0),
    ("0-1", 0, 1),
    ("1-1", 1, 1),
    ("1-3", 1, 3),
    ("0-3", 0, 3),
    ("2-4", 2, 4),
)


def g2() -> list[Case]:
    fixture, anchor = "micro", "a"
    edge_label, node_label, key = _meta(fixture)
    kw = dict(edge_label=edge_label, node_label=node_label, key=key, start_val=anchor)
    out: list[Case] = []
    for name, lo, hi in G2_FORMS:
        # "no quantifier" is a single unquantified step, which the oracle expresses as
        # exactly one repetition.
        rlo, rhi = (1, 1) if lo is None else (lo, hi)
        segs = [dict(lo=lo, hi=hi, direction="right")]
        for restrictor in ("WALK", "TRAIL"):
            out.append(Case(
                id=f"g2-{name}-{restrictor.lower()}",
                construct=f"quantifier {name} under {restrictor}",
                fixture=fixture,
                ref=PathPattern(start=_start(fixture, anchor),
                                segments=(_seg(fixture, rlo, rhi),),
                                restrictor=restrictor, selector="ALL"),
                cypher=render.cypher_common(segs, restrictor=restrictor, **kw),
                cypher_gql=render.cypher_query(segs, restrictor=restrictor, **kw),
                cypher_qpp=render.cypher_query(segs, restrictor=restrictor,
                                               spelling="qpp", **kw),
                pgq=render.pgq_query(segs, restrictor=restrictor, **kw),
                gql=render.gql_query(segs, restrictor=restrictor, **kw),
                group="G2",
                clause=CLAUSE_QUANT,
                note=f"G2 quantifier form {name} under {restrictor}.",
            ))
    return out


# ---------------------------------------------------------------------------
# G3 -- pattern shape
# ---------------------------------------------------------------------------

def _shape_specs():
    """(name, fixture, anchor, segs-for-render, segs-for-oracle, note)."""
    yield ("single", "micro", "a",
           [dict(lo=1, hi=3, direction="right")],
           lambda f: (_seg(f, 1, 3),),
           "control: one quantified segment")
    yield ("two-segment", "micro", "a",
           [dict(lo=1, hi=2, direction="right"), dict(lo=1, hi=2, direction="right")],
           lambda f: (_seg(f, 1, 2), _seg(f, 1, 2)),
           "two concatenated quantified segments: the shape of the standard's own "
           "worked example, and the only shape in which restrictor scope -- whole "
           "pattern or per segment -- is observable")
    yield ("dir-left", "micro", "b",
           [dict(lo=1, hi=3, direction="left")],
           lambda f: (_seg(f, 1, 3, "left"),),
           "reverse traversal")
    yield ("dir-any", "single", "u",
           [dict(lo=2, hi=2, direction="any")],
           lambda f: (_seg(f, 2, 2, "any"),),
           "an undirected step over a directed edge: may a two-step walk re-cross the "
           "edge it arrived on? Under WALK yes, under TRAIL no")
    # Asked with a property rather than a second label. v1's `interior-node-unconstrained`
    # asks the same question with the standard's label expression `:N&Mark`, which three
    # dialects cannot parse. Running both separates "does not implement label
    # expressions" from "binds interior nodes wrongly" -- two different defects that the
    # label form alone reports as one.
    yield ("interior-pred", "tagged", "p",
           [dict(lo=2, hi=2, direction="right")],
           lambda f: (QuantifiedSegment(
               EdgePattern(labels=(fixtures.EDGE_LABEL[f],), direction="right"),
               NodePattern(labels=(fixtures.PRIMARY_LABEL[f],),
                           where=lambda n: n.prop("tag") == "Mark"), 2, 2),),
           "the segment's node pattern constrains the node at the end of the "
           "repetition, not the nodes passed through")
    yield ("self-loop", "loop", "x",
           [dict(lo=1, hi=3, direction="right")],
           lambda f: (_seg(f, 1, 3),),
           "a self-loop is one edge and one node repeated")
    yield ("parallel", "micro", "a",
           [dict(lo=1, hi=1, direction="right")],
           lambda f: (_seg(f, 1, 1),),
           "two edges with the same endpoints are two paths, not one")
    yield ("cycle2", "cycle2", "m",
           [dict(lo=1, hi=4, direction="right")],
           lambda f: (_seg(f, 1, 4),),
           "a 2-cycle traversed twice separates WALK from TRAIL using forward edges only")


def g3() -> list[Case]:
    out: list[Case] = []
    for name, fixture, anchor, segs, oracle_segs, note in _shape_specs():
        edge_label, node_label, key = _meta(fixture)
        kw = dict(edge_label=edge_label, node_label=node_label, key=key,
                  start_val=anchor)
        extra = "y.tag='Mark'" if name == "interior-pred" else None
        kw["extra_where"] = extra
        for restrictor in ("WALK", "TRAIL"):
            out.append(Case(
                id=f"g3-{name}-{restrictor.lower()}",
                construct=f"shape {name} under {restrictor}",
                fixture=fixture,
                ref=PathPattern(start=_start(fixture, anchor),
                                segments=oracle_segs(fixture),
                                restrictor=restrictor, selector="ALL"),
                cypher=render.cypher_common(segs, restrictor=restrictor, **kw),
                cypher_gql=render.cypher_query(segs, restrictor=restrictor, **kw),
                cypher_qpp=render.cypher_query(segs, restrictor=restrictor,
                                               spelling="qpp", **kw),
                pgq=render.pgq_query(segs, restrictor=restrictor, **kw),
                gql=render.gql_query(segs, restrictor=restrictor, **kw),
                group="G3",
                clause=(CLAUSE_INTERIOR if name == "interior-pred" else CLAUSE_QUANT),
                note=f"G3 {note}.",
            ))
    return out


# ---------------------------------------------------------------------------
# G4 -- what the standard requires to be rejected
# ---------------------------------------------------------------------------

# Sec. 5: "every unbounded quantifier must be contained in the scope of either a
# restrictor or a selector or both". A pattern that breaks the rule is ill-formed, and
# an engine that runs it anyway is non-conforming in a direction no answer comparison
# can see. The controls are not decoration: a grid where every case must be rejected is
# passed perfectly by an engine that rejects everything.
G4_CASES = (
    # (name, lo, hi, restrictor, selector, expect, why)
    ("star-walk-all", 0, UNBOUNDED, "WALK", "ALL", "REJECT",
     "unbounded `*` with neither a restrictor nor a selector in scope"),
    ("plus-walk-all", 1, UNBOUNDED, "WALK", "ALL", "REJECT",
     "unbounded `+` with neither a restrictor nor a selector in scope"),
    ("lower-bound-open-walk-all", 2, UNBOUNDED, "WALK", "ALL", "REJECT",
     "unbounded `{2,}` with neither a restrictor nor a selector in scope"),
    ("star-trail-all", 0, UNBOUNDED, "TRAIL", "ALL", "ACCEPT",
     "control: the restrictor bounds the answer, so this is well-formed"),
    ("star-walk-any-shortest", 0, UNBOUNDED, "WALK", "ANY SHORTEST", "ACCEPT",
     "control: the selector bounds the answer, so this is well-formed"),
    ("star-walk-any", 0, UNBOUNDED, "WALK", "ANY", "ACCEPT",
     "control: a selector is in scope, so the standard admits it. Its admissible set "
     "is infinite, so no reference answer exists and acceptance is the whole test"),
)


def g4() -> list[Case]:
    fixture, anchor = "micro", "a"
    edge_label, node_label, key = _meta(fixture)
    kw = dict(edge_label=edge_label, node_label=node_label, key=key, start_val=anchor)
    out: list[Case] = []
    for name, lo, hi, restrictor, selector, expect, why in G4_CASES:
        segs = [dict(lo=lo, hi=hi, direction="right")]
        # An ill-formed case must name WALK out loud. Written with no keyword the query
        # is the dialect's default mode, which for openCypher is TRAIL -- well-formed,
        # and a different question. Common-dialect openCypher has no WALK keyword, so
        # those cells are INEXPRESSIBLE rather than counted against the engine.
        ill = expect == "REJECT"
        kw4 = dict(kw, explicit_walk=ill)
        out.append(Case(
            id=f"g4-{name}",
            construct=f"well-formedness: {why}",
            fixture=fixture,
            ref=PathPattern(start=_start(fixture, anchor),
                            segments=(_seg(fixture, lo, hi),),
                            restrictor=restrictor, selector=selector),
            cypher=(None if ill else
                    render.cypher_common(segs, restrictor=restrictor,
                                         selector=selector, **kw)),
            cypher_gql=render.cypher_query(segs, restrictor=restrictor,
                                           selector=selector, **kw4),
            cypher_qpp=render.cypher_query(segs, restrictor=restrictor,
                                           selector=selector, spelling="qpp", **kw4),
            pgq=render.pgq_query(segs, restrictor=restrictor, selector=selector, **kw4),
            gql=render.gql_query(segs, restrictor=restrictor, selector=selector, **kw4),
            group="G4",
            clause=CLAUSE_UNBOUNDED,
            expect=expect,
            note=f"G4 {why}.",
        ))
    return out


# ---------------------------------------------------------------------------
# G5 -- spelling equivalences
# ---------------------------------------------------------------------------

# Two ways of writing one quantifier. The standard fixes what each means, so an
# engine that answers them differently contradicts itself, and the contradiction is
# visible without any reference semantics at all.
#
# The bare `*` is the case that matters. GQL and SQL/PGQ define it as {0,}; openCypher
# defines it as {1,}. A query ported across that line silently gains or loses every
# zero-length path, which is exactly one row per starting node -- small enough to look
# like a rounding difference and large enough to change a COUNT.
G5_CASES = (
    ("star-bare", 0, "bare", "`*` -- {0,} in GQL and SQL/PGQ, {1,} in openCypher"),
    ("star-explicit", 0, "explicit", "`*0..` / `{0,}` -- unambiguous in both"),
    ("plus-bare", 1, "bare", "`+` -- {1,} in GQL and SQL/PGQ"),
    ("plus-explicit", 1, "explicit", "`*1..` / `{1,}` -- unambiguous in both"),
)

_BARE_LEGACY = {0: "*", 1: "*"}          # openCypher writes both as a bare `*`
_BARE_QPP = {0: "*", 1: "+"}
_BARE_PGQ = {0: "*", 1: "+"}


def g5() -> list[Case]:
    fixture, anchor, restrictor = "micro", "a", "TRAIL"
    edge_label, node_label, key = _meta(fixture)
    kw = dict(edge_label=edge_label, node_label=node_label, key=key, start_val=anchor)
    out: list[Case] = []
    for name, lo, spelling, why in G5_CASES:
        segs = [dict(lo=lo, hi=UNBOUNDED, direction="right")]
        if spelling == "explicit":
            cy = render.cypher_common(segs, restrictor=restrictor, **kw)
            gql = render.cypher_query(segs, restrictor=restrictor, **kw)
            qpp = render.cypher_query(segs, restrictor=restrictor, spelling="qpp", **kw)
            pgq = render.pgq_query(segs, restrictor=restrictor, **kw)
            gqlq = render.gql_query(segs, restrictor=restrictor, **kw)
        else:
            # Hand-written on purpose: the point of the case is the exact symbol.
            cy = (f"MATCH p=(x:{node_label})-[:{edge_label}{_BARE_LEGACY[lo]}]->"
                  f"(y:{node_label}) WHERE x.{key}='{anchor}' {render.RETURN_COLS}")
            gql = (f"MATCH {restrictor} (x:{node_label})-[:{edge_label}"
                   f"{_BARE_LEGACY[lo]}]->(y:{node_label}) "
                   f"WHERE x.{key}='{anchor}' {render.RETURN_COLS}")
            qpp = (f"MATCH {restrictor} (x:{node_label}) "
                   f"(()-[:{edge_label}]->()){_BARE_QPP[lo]} (y:{node_label}) "
                   f"WHERE x.{key}='{anchor}' {render.RETURN_COLS}")
            pgq = (f"FROM GRAPH_TABLE(g MATCH {restrictor} (x:{node_label})"
                   f"-[e0:{edge_label}]->{_BARE_PGQ[lo]}(y:{node_label}) "
                   f"WHERE x.{key}='{anchor}' {render.PGQ_COLS}")
            gqlq = (f"MATCH {restrictor} (x:{node_label})-[:{edge_label}]->"
                    f"{_BARE_PGQ[lo]}(y:{node_label}) "
                    f"WHERE x.{key}='{anchor}' {render.RETURN_COLS}")
        out.append(Case(
            id=f"g5-{name}",
            construct=f"quantifier spelling: {why}",
            fixture=fixture,
            ref=PathPattern(start=_start(fixture, anchor),
                            segments=(_seg(fixture, lo, UNBOUNDED),),
                            restrictor=restrictor, selector="ALL"),
            cypher=cy, cypher_gql=gql, cypher_qpp=qpp, pgq=pgq, gql=gqlq,
            group="G5",
            clause="Deutsch et al. Sec. 5: `*` abbreviates {0,} and `+` abbreviates {1,}",
            note=f"G5 {why}. Paired with its sibling: an engine that answers the two "
                 f"differently contradicts itself.",
        ))
    return out


# Pairs whose two members must return the same answer, whatever that answer is. Ids
# are resolved through suite_all.resolve() before use: `g5-star-explicit` is the same
# query as the G4 control and is run under that id.
G5_PAIRS = (("g5-star-bare", "g5-star-explicit"),
            ("g5-plus-bare", "g5-plus-explicit"))

ALL_V2 = g1() + g2() + g3() + g4() + g5()
BY_ID_V2 = {c.id: c for c in ALL_V2}
