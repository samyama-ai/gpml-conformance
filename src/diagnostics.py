"""Classify what an engine said alongside an answer, and check whether it was true.

Issue #2 proposes S2b: how often a divergence is delivered with *neither* an error
nor a diagnostic. Two things have to be right before that number means anything, and
the first measurement showed both are load-bearing rather than theoretical.

**Relevance.** Memgraph attaches a diagnostic to 12 of the 12 cells it answers. Every
one is `PlanHinting` -- "consider creating a label-property index". It is a
performance hint and says nothing about the answer being ambiguous. Counting it as
"the user was told" would be wrong, and nobody was even trying to game the metric.
So a diagnostic counts only when it is *about the disagreement*, and the default for
anything unclassifiable is that it does not count. That default runs against the
engine, which is the safe direction for an author measuring their own product.

**Truth.** A diagnostic is a claim, and a claim can be checked. `PathModeAffectsResult`
asserts that naming the path mode would change the answer. Where an engine can express
both modes, that is falsifiable by asking it: run the same pattern under each and see
whether the answers differ. We do not credit an engine for a warning we have not
verified.
"""
from __future__ import annotations
import re
from typing import Optional

# Codes and phrasings that mark a diagnostic as operational -- about how the query
# ran, not about what it means. Matched case-insensitively against code and title.
OPERATIONAL = re.compile(
    r"planhint|hint|index|performance|deprecat|cartesian|unrecognized|unbounded"
    r"|eager|memory|runtime|slow|scan will be used|consider creating",
    re.I)

# Phrasings that mark a diagnostic as being about path semantics -- the construct
# these divergences are actually about.
SEMANTIC_PATH = re.compile(
    r"path mode|pathmode|walk|trail|acyclic|simple|relationship uniqueness"
    r"|quantified pattern|39075",
    re.I)


def classify(diag: dict) -> tuple[str, str]:
    """-> (kind, why). kind is 'semantic', 'operational' or 'unclassified'."""
    blob = " ".join(str(diag.get(k, "")) for k in ("code", "title", "description"))
    if OPERATIONAL.search(blob) and not SEMANTIC_PATH.search(blob):
        return "operational", "names a plan, index or performance concern only"
    if SEMANTIC_PATH.search(blob):
        return "semantic", "names the path-mode construct the divergence is about"
    return "unclassified", "does not name the construct; not credited"


def speaks_about_divergence(diagnostics: Optional[list]) -> bool:
    """Did the engine say something *about the disagreement*?

    None (no channel) and [] (asked, said nothing) both count as not speaking; the
    map records which it was, but for this question they have the same answer.
    """
    for d in (diagnostics or []):
        if classify(d)[0] == "semantic":
            return True
    return False


def verify_path_mode_claim(engine, case, fixtures) -> Optional[bool]:
    """Is `PathModeAffectsResult` true for this case? None if unverifiable.

    The claim is that naming the mode would change the answer. Ask the engine both
    ways. Only meaningful for an engine that can express both modes explicitly.
    """
    q = case.cypher
    if not q or "*" not in q:
        return None
    walk = re.sub(r"MATCH\s+(p=)?", lambda m: f"MATCH {m.group(1) or ''}WALK ", q, count=1)
    trail = re.sub(r"MATCH\s+(p=)?", lambda m: f"MATCH {m.group(1) or ''}TRAIL ", q, count=1)
    try:
        g = fixtures.FIXTURES[case.fixture]()
        engine.load(g, fixtures.PRIMARY_LABEL[case.fixture],
                    fixtures.EDGE_LABEL[case.fixture])
        a = engine.run(walk).pairs
        b = engine.run(trail).pairs
    except Exception:
        return None
    return a != b
