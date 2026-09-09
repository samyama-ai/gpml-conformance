"""Probe which GQL path-prefix syntax an engine accepts, instead of hardcoding it.

When this suite started, no engine took the standard's restrictor and selector
keywords, so every such case scored INEXPRESSIBLE and a single hardcoded set was
enough. That is no longer true, and the two engines that do take them **disagree
about the syntax**:

  Samyama-Graph 1.7.1   `MATCH ACYCLIC (x)-[:E*1..3]->(y)`      -- legacy quantifier
  Neo4j 2026.04         `MATCH ACYCLIC (x) (()-[:E]->()){1,3} (y)`  -- quantified path
                        pattern only; the same query with `*1..3` is refused, and the
                        error names the legacy quantifier as the reason.

A hardcoded list would have to encode that, would go stale, and would quietly decide
which engine gets measured on which construct. So we ask each engine at startup, on a
two-node graph, and record the answer in the map beside the results it explains.

The probe is deliberately narrow: it asks only *does this parse and return rows*, and
never what the rows were. Capability is a question about syntax. Whether the answer is
right is what the rest of the suite is for.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

from graph import PropertyGraph


def _probe_graph() -> PropertyGraph:
    """m -> n -> m. Two nodes, two edges, enough for any quantified pattern."""
    g = PropertyGraph()
    for n in ("m", "n"):
        g.add_node(n, labels=("N",), name=n)
    g.add_edge("e1", "m", "n", labels=("E",))
    g.add_edge("e2", "n", "m", labels=("E",))
    return g


# (name, query). `{L}` and `{E}` are filled with the probe fixture's labels.
LEGACY = "MATCH {prefix}(x:{L})-[:{E}*1..2]->(y:{L}) RETURN x.eid AS s, y.eid AS t"
QPP = ("MATCH {prefix}(x:{L}) (()-[:{E}]->()){{1,2}} (y:{L}) "
       "RETURN x.eid AS s, y.eid AS t")


@dataclass
class GqlSyntax:
    """Which spellings of the standard's path prefixes an engine accepts."""

    restrictor_legacy: bool = False      # ACYCLIC with -[:E*1..2]->
    restrictor_qpp: bool = False         # ACYCLIC with (()-[:E]->()){1,2}
    selector_legacy: bool = False        # ANY SHORTEST with -[:E*1..2]->
    selector_qpp: bool = False           # ANY SHORTEST with the quantified form
    named_path_after_prefix: bool = False  # `TRAIL p = (...)`, the standard's order

    def takes_prefixes(self) -> bool:
        return any((self.restrictor_legacy, self.restrictor_qpp,
                    self.selector_legacy, self.selector_qpp))

    def as_dict(self) -> dict:
        return asdict(self)


def probe(engine) -> GqlSyntax:
    """Ask one engine what it parses. Never raises: a refusal is the answer."""
    if engine.dialect != "cypher":
        return GqlSyntax()
    g = _probe_graph()
    try:
        engine.load(g, "N", "E")
    except Exception:
        return GqlSyntax()

    def accepts(template: str, prefix: str) -> bool:
        q = template.format(prefix=prefix, L="N", E="E")
        try:
            engine.run(q)
            return True
        except Exception:
            return False

    caps = GqlSyntax(
        restrictor_legacy=accepts(LEGACY, "ACYCLIC "),
        restrictor_qpp=accepts(QPP, "ACYCLIC "),
        selector_legacy=accepts(LEGACY, "ANY SHORTEST "),
        selector_qpp=accepts(QPP, "ANY SHORTEST "),
    )
    # The standard writes `TRAIL p = (...)`. Ask in whichever quantifier spelling the
    # engine took above, so a refusal here is about the *order*, not the quantifier.
    if caps.restrictor_legacy or caps.restrictor_qpp:
        tmpl = LEGACY if caps.restrictor_legacy else QPP
        q = tmpl.format(prefix="ACYCLIC p = ", L="N", E="E")
        try:
            engine.run(q)
            caps.named_path_after_prefix = True
        except Exception:
            caps.named_path_after_prefix = False
    return caps
