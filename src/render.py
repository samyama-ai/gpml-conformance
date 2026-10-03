"""Surface-syntax renderers: one abstract pattern, four dialect spellings.

v1 wrote every query string by hand. That is fine for 17 cases and wrong for 60: the
strings drift, and a reader cannot tell whether two cases differ because the construct
differs or because the author typed them differently. Here the spelling is a function of
the construct, so two cases differ only where the construct does.

Four renderings, matching what the runner asks for:

  cypher      openCypher that every engine in the matrix can parse. Exists only where
              the dialect has a way to say the construct -- no restrictor keyword, no
              selector keyword except the ALL SHORTEST rewrite. Otherwise None, and the
              cell scores INEXPRESSIBLE rather than being counted against the engine.
  cypher_gql  openCypher plus the standard's restrictor/selector prefixes, with the
              legacy `*lo..hi` quantifier.
  cypher_qpp  the same prefixes with the quantified path pattern `(()-[:E]->()){lo,hi}`.
              Neo4j 2026.04 takes the prefixes only in this spelling.
  pgq         SQL/PGQ GRAPH_TABLE.
"""
from __future__ import annotations

from gpml_ref import UNBOUNDED

ARROW = {"right": ("-[", "]->"), "left": ("<-[", "]-"), "any": ("-[", "]-")}
QPP_ARROW = {"right": "()-[:{e}]->()", "left": "()<-[:{e}]-()", "any": "()-[:{e}]-()"}


def _bounds(lo: int, hi: int, unbounded_as: int | None):
    """Resolve an unbounded upper bound to the finite one the dialect needs.

    A dialect with no `*` must be given a number. The number is never invented: it is
    the sound bound the restrictor itself implies (|E| for TRAIL, |N| for ACYCLIC and
    SIMPLE), computed by the caller and passed in, so the bounded query asks the same
    question as the unbounded one rather than a smaller one.
    """
    if hi != UNBOUNDED:
        return lo, hi
    if unbounded_as is None:
        raise ValueError("unbounded quantifier needs an explicit finite bound to render")
    return lo, unbounded_as


def quant_legacy(lo, hi, unbounded_as=None) -> str:
    """`*lo..hi`, or '' where the construct has no quantifier at all.

    An unbounded quantifier is rendered unbounded -- `*` or `*lo..` -- unless the
    caller supplied a finite bound to substitute. Substituting a bound silently would
    turn a question about unboundedness into a question about a number.
    """
    if lo is None:
        return ""
    if hi == UNBOUNDED and unbounded_as is None:
        # Always write the lower bound. The bare `*` is not the same quantifier in
        # every dialect -- GQL and SQL/PGQ define it as {0,}, openCypher as {1,} --
        # so a generated case that used it would be asking two different questions
        # and calling the difference a divergence. `*0..` and `*1..` are unambiguous
        # and both dialects take them. The bare forms are measured deliberately, as
        # their own construct, in G5.
        return f"*{lo}.."
    lo, hi = _bounds(lo, hi, unbounded_as)
    return f"*{lo}..{hi}"


def quant_pgq(lo, hi) -> str:
    if lo is None:
        return ""
    if hi == UNBOUNDED:
        return f"{{{lo},}}"
    return f"{{{lo},{hi}}}"


def prefix(restrictor: str, selector: str, explicit_walk: bool = False) -> str:
    """The standard's prefix keywords. WALK and ALL are the defaults and are written
    by saying nothing, which is how the standard's own examples write them.

    explicit_walk writes WALK anyway. That matters for exactly one question: whether an
    engine enforces the rule that an unbounded quantifier needs a restrictor or a
    selector in scope. Written without the keyword, the query is indistinguishable from
    the dialect's own default mode -- for openCypher that default is TRAIL, which makes
    the pattern well-formed and the question unasked. WALK has to be said out loud.
    """
    parts = [p for p in (("" if restrictor == "WALK" and not explicit_walk else restrictor),
                         ("" if selector == "ALL" else selector)) if p]
    return (" ".join(parts) + " ") if parts else ""


def _where(fixture_key: str, start_val: str, extra: str | None) -> str:
    w = f"x.{fixture_key}='{start_val}'"
    return f"{w} AND {extra}" if extra else w


def cypher_pattern(segs, edge_label, node_label, unbounded_as=None) -> str:
    """`(x:N)-[:E*1..3]->(y:N)`, or the two-segment form, in legacy spelling."""
    out = [f"(x:{node_label})"]
    for i, s in enumerate(segs):
        open_, close = ARROW[s["direction"]]
        var = s.get("edge_var", "")
        q = quant_legacy(s["lo"], s["hi"], unbounded_as)
        end = "y" if i == len(segs) - 1 else f"m{i}"
        lab = f":{node_label}" if s.get("end_label") is None else f":{s['end_label']}"
        out.append(f"{open_}{var}:{edge_label}{q}{close}({end}{lab})")
    return "".join(out)


def qpp_pattern(segs, edge_label, node_label, unbounded_as=None) -> str:
    """`(x:N) (()-[:E]->()){1,3} (y:N)` -- the quantified-path-pattern spelling."""
    out = [f"(x:{node_label})"]
    for i, s in enumerate(segs):
        step = QPP_ARROW[s["direction"]].format(e=edge_label)
        if s["lo"] is None:
            q = ""
        elif s["hi"] == UNBOUNDED and unbounded_as is None:
            # Explicit, for the same reason as the legacy spelling above.
            q = f"{{{s['lo']},}}"
        else:
            lo, hi = _bounds(s["lo"], s["hi"], unbounded_as)
            q = f"{{{lo},{hi}}}"
        end = "y" if i == len(segs) - 1 else f"m{i}"
        lab = f":{node_label}" if s.get("end_label") is None else f":{s['end_label']}"
        out.append(f"({step}){q} ({end}{lab})")
    return " ".join(out)


def pgq_pattern(segs, edge_label, node_label) -> str:
    out = [f"(x:{node_label})"]
    for i, s in enumerate(segs):
        open_, close = ARROW[s["direction"]]
        var = s.get("edge_var") or f"e{i}"
        pred = f" WHERE {s['edge_where_pgq']}" if s.get("edge_where_pgq") else ""
        end = "y" if i == len(segs) - 1 else f"m{i}"
        lab = f":{node_label}" if s.get("end_label") is None else f":{s['end_label']}"
        out.append(f"{open_}{var}:{edge_label}{pred}{close}{quant_pgq(s['lo'], s['hi'])}({end}{lab})")
    return "".join(out)


RETURN_COLS = "RETURN x.eid AS s, y.eid AS t"
PGQ_COLS = "COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t"


def cypher_query(segs, *, edge_label, node_label, key, start_val,
                 restrictor="WALK", selector="ALL", extra_where=None,
                 unbounded_as=None, spelling="legacy", explicit_walk=False) -> str | None:
    """The openCypher text, or None where the dialect cannot say it.

    None is not a failing grade. A dialect with no ACYCLIC keyword is not wrong about
    ACYCLIC; it is silent, and silence scores INEXPRESSIBLE.
    """
    pat = (cypher_pattern if spelling == "legacy" else qpp_pattern)(
        segs, edge_label, node_label, unbounded_as)
    where = _where(key, start_val, extra_where)
    return (f"MATCH {prefix(restrictor, selector, explicit_walk)}{pat} "
            f"WHERE {where} {RETURN_COLS}")


def cypher_common(segs, *, edge_label, node_label, key, start_val,
                  restrictor="WALK", selector="ALL", extra_where=None,
                  unbounded_as=None) -> str | None:
    """The rendering every openCypher engine in the matrix can parse.

    Exists for exactly two shapes:
      * restrictor WALK or TRAIL with selector ALL -- written with no keyword at all,
        which is the point of the pair: the one query has two possible meanings and the
        suite asks which one the engine gives it.
      * selector ALL SHORTEST -- openCypher has no keyword, but the meaning is
        expressible by taking the minimum path length per endpoint pair and re-matching.
    Everything else returns None.
    """
    if restrictor not in ("WALK", "TRAIL"):
        return None
    pat = cypher_pattern(segs, edge_label, node_label, unbounded_as)
    where = _where(key, start_val, extra_where)
    if selector == "ALL":
        return f"MATCH p={pat} WHERE {where} {RETURN_COLS}"
    if selector == "ALL SHORTEST":
        bare = pat.replace(f"(x:{node_label})", "(x)").replace(f"(y:{node_label})", "(y)")
        return (f"MATCH p={pat} WHERE {where} "
                f"WITH x, y, min(length(p)) AS m "
                f"MATCH q={bare} WHERE length(q)=m {RETURN_COLS}")
    return None


def pgq_query(segs, *, edge_label, node_label, key, start_val,
              restrictor="WALK", selector="ALL", extra_where=None,
              explicit_walk=False) -> str:
    pat = pgq_pattern(segs, edge_label, node_label)
    where = _where(key, start_val, extra_where)
    return (f"FROM GRAPH_TABLE(g MATCH {prefix(restrictor, selector, explicit_walk)}{pat} "
            f"WHERE {where} {PGQ_COLS}")
