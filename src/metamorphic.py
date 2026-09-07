"""Mode-independent self-consistency checks.

The conformance map compares an engine to a reference semantics. That comparison
is only as persuasive as the reading of the standard behind it, and where a dialect
deliberately deviates (openCypher's relationship uniqueness) it says nothing about
whether the engine is *correct*.

These checks need no reference and no reading. They are metamorphic relations that
hold for a quantified path pattern under **every** path mode in the standard --
WALK, TRAIL, ACYCLIC and SIMPLE alike -- because none of the restrictors mentions
the quantifier bounds. An engine that breaks one is inconsistent with itself.

  M1  widening the upper bound cannot lose answers
        A(lo, hi)  is a sub-multiset of  A(lo, hi+1)
      True in every mode: the set of paths of length in [lo,hi] is contained in
      the set of length in [lo,hi+1], and the restrictor filters paths pointwise.

  M2  widening the lower bound downwards cannot lose answers
        A(lo, hi)  is a sub-multiset of  A(lo-1, hi)

  M3  a range decomposes into its exact lengths
        A(lo, hi)  ==  sum over k in [lo,hi] of  A(k, k)
      Again pointwise: each path has exactly one length.

Violations are reported with the exact pair of queries that disagree.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Violation:
    relation: str
    left: str
    right: str
    left_answer: dict
    right_answer: dict
    explanation: str


def _sub_multiset(a: Counter, b: Counter) -> bool:
    return all(b[k] >= v for k, v in a.items())


def check_engine(run: Callable[[int, int], Optional[Counter]],
                 lo_hi_pairs, max_len: int) -> list[Violation]:
    """`run(lo, hi)` returns the engine's endpoint multiset, or None if it refused."""
    answers: dict[tuple[int, int], Counter] = {}
    for lo, hi in lo_hi_pairs:
        a = run(lo, hi)
        if a is not None:
            answers[(lo, hi)] = a

    v: list[Violation] = []

    for (lo, hi), a in answers.items():
        b = answers.get((lo, hi + 1))
        if b is not None and not _sub_multiset(a, b):
            v.append(Violation(
                "M1 upper-bound monotonicity", f"{{{lo},{hi}}}", f"{{{lo},{hi+1}}}",
                dict(a), dict(b),
                "widening the upper bound dropped an answer, which no path mode allows"))
        c = answers.get((lo - 1, hi))
        if lo >= 1 and c is not None and not _sub_multiset(a, c):
            v.append(Violation(
                "M2 lower-bound monotonicity", f"{{{lo},{hi}}}", f"{{{lo-1},{hi}}}",
                dict(a), dict(c),
                "widening the lower bound dropped an answer, which no path mode allows"))

    for (lo, hi), a in answers.items():
        if hi - lo < 1 or hi > max_len:
            continue
        parts = [answers.get((k, k)) for k in range(lo, hi + 1)]
        if any(p is None for p in parts):
            continue
        total = Counter()
        for p in parts:
            total.update(p)
        if total != a:
            v.append(Violation(
                "M3 range decomposition", f"{{{lo},{hi}}}",
                " + ".join(f"{{{k},{k}}}" for k in range(lo, hi + 1)),
                dict(a), dict(total),
                "a bounded range is not the sum of its exact lengths, which no path "
                "mode allows"))
    return v
