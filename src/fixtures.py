"""The graphs the suite runs on. Deliberately tiny: every expected answer must be
checkable by hand, and every divergence must be a one-screen reproducer."""
from __future__ import annotations
from graph import PropertyGraph

OWNER = {"a1": "Scott", "a2": "Aretha", "a3": "Mike",
         "a4": "Charles", "a5": "Natalia", "a6": "Dave"}

FIG1_TRANSFERS = [("t1", "a1", "a3"), ("t2", "a3", "a2"), ("t3", "a2", "a4"),
                  ("t4", "a4", "a6"), ("t5", "a6", "a3"), ("t6", "a6", "a5"),
                  ("t7", "a3", "a5"), ("t8", "a5", "a1")]


def fig1() -> PropertyGraph:
    """The Transfer sub-graph of Figure 1 of arXiv:2112.06217 (see RECONSTRUCTION.md)."""
    g = PropertyGraph()
    for aid, owner in OWNER.items():
        g.add_node(aid, labels=("Account",), owner=owner)
    for eid, s, d in FIG1_TRANSFERS:
        g.add_edge(eid, s, d, labels=("Transfer",))
    return g


def micro() -> PropertyGraph:
    """Parallel edges plus a directed 3-cycle.

        a =e1,e2=> b --e3--> c --e4--> a
    """
    g = PropertyGraph()
    for n in ("a", "b", "c"):
        g.add_node(n, labels=("N",), name=n)
    for eid, s, d in [("e1", "a", "b"), ("e2", "a", "b"),
                      ("e3", "b", "c"), ("e4", "c", "a")]:
        g.add_edge(eid, s, d, labels=("E",))
    return g


def loop() -> PropertyGraph:
    """A self-loop and a 2-cycle.

        x --e1--> x   (self-loop)
        x --e2--> y --e3--> x
    """
    g = PropertyGraph()
    for n in ("x", "y"):
        g.add_node(n, labels=("N",), name=n)
    g.add_edge("e1", "x", "x", labels=("E",))
    g.add_edge("e2", "x", "y", labels=("E",))
    g.add_edge("e3", "y", "x", labels=("E",))
    return g


def cycle2() -> PropertyGraph:
    """A directed 2-cycle: m --e1--> n --e2--> m.

    Under WALK a forward-only quantifier {1,4} from m yields four paths, because
    e1 and e2 may each be traversed twice. Under TRAIL it yields two. Nothing else
    in the suite separates the two modes using only forward edges.
    """
    g = PropertyGraph()
    for n in ("m", "n"):
        g.add_node(n, labels=("N",), name=n)
    g.add_edge("e1", "m", "n", labels=("E",))
    g.add_edge("e2", "n", "m", labels=("E",))
    return g


def single() -> PropertyGraph:
    """One directed edge. Used to ask whether a two-step any-direction walk may
    traverse the same edge back, which the standard's WALK mode permits."""
    g = PropertyGraph()
    g.add_node("u", labels=("N",), name="u")
    g.add_node("v", labels=("N",), name="v")
    g.add_edge("e1", "u", "v", labels=("E",))
    return g


def tagged() -> PropertyGraph:
    """A 2-hop chain whose interior node lacks the label carried by the endpoints.

        p:N,Mark  -->  q:N        -->  r:N,Mark
    """
    g = PropertyGraph()
    g.add_node("p", labels=("N", "Mark"), name="p")
    g.add_node("q", labels=("N",), name="q")
    g.add_node("r", labels=("N", "Mark"), name="r")
    g.add_edge("e1", "p", "q", labels=("E",))
    g.add_edge("e2", "q", "r", labels=("E",))
    return g


FIXTURES = {"fig1": fig1, "micro": micro, "loop": loop, "cycle2": cycle2,
            "single": single, "tagged": tagged}


# The primary label of each fixture -- the label every node carries, used as the
# table/vertex-table name by engines whose data model has no multi-label nodes.
PRIMARY_LABEL = {"fig1": "Account", "micro": "N", "loop": "N",
                 "cycle2": "N", "single": "N", "tagged": "N"}

# The edge label of each fixture, used as the relationship-table name.
EDGE_LABEL = {"fig1": "Transfer", "micro": "E", "loop": "E",
              "cycle2": "E", "single": "E", "tagged": "E"}

# The node property each fixture identifies nodes by in query text.
KEY_PROP = {"fig1": "owner", "micro": "name", "loop": "name",
            "cycle2": "name", "single": "name", "tagged": "name"}
