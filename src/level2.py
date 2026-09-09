"""Compare answers as multisets of *edge sequences*, not just endpoint pairs.

The map's headline comparison is level 1: the multiset of (start, end) identifier
pairs. Every engine can produce that, which is what keeps the comparison fair across
dialects that cannot return a path object at all. The paper states the cost plainly:
endpoint-level comparison **can only under-count divergence**, because two engines can
agree on which endpoints are reachable and still disagree about which paths got there.

This module closes that gap where it can be closed. Level 2 asks each engine for the
ordered edge identifiers of every matched path and compares those multisets instead.
The reference semantics already carries them -- `Path.edges` -- so the expected answer
costs nothing new; only the engine side needs work.

Two things it deliberately does not do:

  * It does not replace level 1. An engine with no path object still has to be
    measurable, and the headline has to stay comparable across all of them.
  * It does not credit or penalise an engine for the *representation*. Kùzu returns
    whole edge records, Bolt engines return whatever the projection asks for; each
    adapter normalises to a tuple of edge ids, and anything that cannot be normalised
    is reported as unavailable rather than guessed at.

A cell that conforms at level 1 and diverges at level 2 is the interesting case: the
engine returned the right endpoints by the wrong paths, and nothing in the headline
comparison would have shown it.
"""
from __future__ import annotations
import re
from collections import Counter
from typing import Optional

# The edge-id projection, per dialect. `{L}`/`{E}` are the fixture's labels.
#
# Bolt engines and Samyama take the openCypher list comprehension over
# `relationships(p)`. Kùzu binds the variable-length relationship itself and needs
# `rels(<var>)`, which returns whole edge records -- normalised below.
CYPHER_L2 = ("MATCH p=(x:{L})-[:{E}*{lo}..{hi}]->(y:{L}) WHERE x.{key}='{start}' "
             "RETURN x.eid AS s, [r IN relationships(p) | r.eid] AS t")
KUZU_L2 = ("MATCH p=(x:{L})-[e:{E}*{lo}..{hi}]->(y:{L}) WHERE x.{key}='{start}' "
           "RETURN x.eid AS s, rels(e) AS t")

_EID = re.compile(r"'eid':\s*'([^']+)'")


def normalise(raw) -> Optional[tuple]:
    """Turn whatever the engine returned into a tuple of edge ids, or None.

    Accepts a real list of strings, a stringified list of strings, or Kùzu's list of
    edge records. Returns None when the shape is unrecognised, which is reported as
    unavailable -- never silently treated as an empty path, which would read as a
    divergence the engine did not commit.
    """
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and "eid" in item:
                out.append(item["eid"])
            else:
                return None
        return tuple(out)
    if isinstance(raw, str):
        s = raw.strip()
        if not s.startswith("["):
            return None
        if s in ("[]", "[ ]"):
            return ()                          # a genuinely zero-length path
        ids = _EID.findall(s)                  # Kùzu record form
        if ids:
            return tuple(ids)
        # A stringified list. Apache AGE renders agtype as JSON, so its ids are
        # double-quoted; Python reprs are single-quoted. Accept either.
        #
        # This branch used to try single quotes only and fall through to an empty
        # tuple, which read as "the engine returned zero-length paths" and produced
        # five false divergences against Apache AGE before anyone looked. An
        # unrecognised shape must be unavailable, never empty.
        ids = re.findall(r"""["']([^"']*)["']""", s)
        return tuple(ids) if ids else None
    return None


def reference_edge_multiset(result) -> Optional[Counter]:
    """The expected multiset of edge sequences, or None if the selector is free.

    A nondeterministic selector fixes how many paths come back per endpoint pair, not
    which, so there is no single expected multiset. Those cells are checked against the
    admissible set instead, exactly as at level 1.
    """
    if not result.deterministic:
        return None
    return Counter(tuple(p.edges) for p in result.exact)


def admissible_edge_sequences(result) -> set:
    return {tuple(p.edges) for p in result.admissible}
