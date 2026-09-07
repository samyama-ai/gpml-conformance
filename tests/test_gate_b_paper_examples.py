"""Gate B: the reference semantics must reproduce the published worked answers.

Source of truth: Deutsch et al., "Graph Pattern Matching in GQL and SQL/PGQ"
(SIGMOD 2022, arXiv:2112.06217), Sec. 5.1. The paper prints the exact path
bindings its queries return over the property graph of its Figure 1. If our
enumerator does not reproduce those bindings character for character, the
oracle is wrong and nothing downstream may be claimed.

The Transfer sub-graph of Figure 1 is reconstructed from the paths the paper
itself prints; each edge below is witnessed by at least one printed path
(see RECONSTRUCTION.md for the derivation).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph import PropertyGraph
from gpml_ref import (EdgePattern, NodePattern, PathPattern, QuantifiedSegment,
                      UNBOUNDED, match)

OWNER = {"a1": "Scott", "a2": "Aretha", "a3": "Mike",
         "a4": "Charles", "a5": "Natalia", "a6": "Dave"}

TRANSFERS = [("t1", "a1", "a3"), ("t2", "a3", "a2"), ("t3", "a2", "a4"),
             ("t4", "a4", "a6"), ("t5", "a6", "a3"), ("t6", "a6", "a5"),
             ("t7", "a3", "a5"), ("t8", "a5", "a1")]


def fig1() -> PropertyGraph:
    g = PropertyGraph()
    for aid, owner in OWNER.items():
        g.add_node(aid, labels=("Account",), owner=owner)
    for eid, s, d in TRANSFERS:
        g.add_edge(eid, s, d, labels=("Transfer",))
    return g


def owned_by(name):
    return NodePattern(labels=("Account",), where=lambda n: n.prop("owner") == name)


def transfer_star(target: NodePattern, lo=0):
    return QuantifiedSegment(EdgePattern(labels=("Transfer",), direction="right"),
                             target, lo, UNBOUNDED)


def rendered(result):
    assert result.exact is not None
    return sorted(p.render() for p in result.exact)


def test_trail_dave_to_aretha():
    """Sec. 5.1: MATCH TRAIL p = (a WHERE a.owner='Dave')-[t:Transfer]->*
                                (b WHERE b.owner='Aretha')
    "returns three bindings for p"."""
    pat = PathPattern(start=owned_by("Dave"),
                      segments=(transfer_star(owned_by("Aretha")),),
                      restrictor="TRAIL", selector="ALL")
    assert rendered(match(fig1(), pat)) == sorted([
        "path(a6,t5,a3,t2,a2)",
        "path(a6,t6,a5,t8,a1,t1,a3,t2,a2)",
        "path(a6,t5,a3,t7,a5,t8,a1,t1,a3,t2,a2)",
    ])


def test_trail_excludes_edge_repeating_path():
    """Sec. 5.1: path(a6,t5,a3,t2,a2,t3,a4,t4,a6,t5,a3,t2,a2) "is not a trail,
    and is thus not returned"."""
    pat = PathPattern(start=owned_by("Dave"),
                      segments=(transfer_star(owned_by("Aretha")),),
                      restrictor="TRAIL", selector="ALL")
    assert "path(a6,t5,a3,t2,a2,t3,a4,t4,a6,t5,a3,t2,a2)" not in rendered(match(fig1(), pat))


def test_any_shortest_dave_to_aretha():
    """Sec. 5.1: MATCH ANY SHORTEST ... "there is only one shortest path between
    these nodes and thus p is bound to path(a6,t5,a3,t2,a2)"."""
    pat = PathPattern(start=owned_by("Dave"),
                      segments=(transfer_star(owned_by("Aretha")),),
                      restrictor="WALK", selector="ANY SHORTEST")
    r = match(fig1(), pat)
    assert not r.deterministic
    assert {p.render() for p in r.admissible} == {"path(a6,t5,a3,t2,a2)"}
    assert sum(r.per_partition_count.values()) == 1


def test_all_shortest_trail_two_segments():
    """Sec. 5.1: MATCH ALL SHORTEST TRAIL
         p = (Dave)-[t:Transfer]->*(Aretha)-[r:Transfer]->*(Mike)
    "returns two bindings for p"."""
    pat = PathPattern(start=owned_by("Dave"),
                      segments=(transfer_star(owned_by("Aretha")),
                                transfer_star(owned_by("Mike"))),
                      restrictor="TRAIL", selector="ALL SHORTEST")
    assert rendered(match(fig1(), pat)) == sorted([
        "path(a6,t5,a3,t2,a2,t3,a4,t4,a6,t6,a5,t8,a1,t1,a3)",
        "path(a6,t6,a5,t8,a1,t1,a3,t2,a2,t3,a4,t4,a6,t5,a3)",
    ])


def test_all_shortest_trail_excludes_shorter_non_trail():
    """Sec. 5.1: "The path path(a6,t5,a3,t2,a2,t3,a4,t4,a6,t5,a3) is not
    considered: it is shorter but it is not a trail"."""
    pat = PathPattern(start=owned_by("Dave"),
                      segments=(transfer_star(owned_by("Aretha")),
                                transfer_star(owned_by("Mike"))),
                      restrictor="TRAIL", selector="ALL SHORTEST")
    assert "path(a6,t5,a3,t2,a2,t3,a4,t4,a6,t5,a3)" not in rendered(match(fig1(), pat))


def test_bounded_quantifier_without_restrictor_is_a_walk():
    """Sec. 5.1 (end): for
         MATCH (p WHERE owner='Natalia')->{1,10}(q WHERE owner='Mike')->{1,10}
               (r WHERE owner='Scott')
    "path(a5,t8,a1,t1,a3,t7,a5,t8,a1) is a solution to this query" -- it repeats
    the edge t8, so a bounded quantifier with no restrictor means WALK.
    The paper adds: it "fails the restrictor TRAIL (as well as SIMPLE and
    ACYCLIC)"."""
    def seg(target):
        return QuantifiedSegment(EdgePattern(direction="right"), target, 1, 10)

    walk = PathPattern(start=owned_by("Natalia"),
                       segments=(seg(owned_by("Mike")), seg(owned_by("Scott"))),
                       restrictor="WALK", selector="ALL")
    assert "path(a5,t8,a1,t1,a3,t7,a5,t8,a1)" in rendered(match(fig1(), walk))

    for r in ("TRAIL", "SIMPLE", "ACYCLIC"):
        restricted = PathPattern(start=owned_by("Natalia"),
                                 segments=(seg(owned_by("Mike")), seg(owned_by("Scott"))),
                                 restrictor=r, selector="ALL")
        assert "path(a5,t8,a1,t1,a3,t7,a5,t8,a1)" not in rendered(match(fig1(), restricted))
