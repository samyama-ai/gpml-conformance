"""Minimal reproducer: Kuzu 0.11.3 mis-evaluates a quantifier with lower bound 0.

Symptom, on a two-node graph with a self-loop:
  * every path whose end node is the start node is returned TWICE
  * the zero-length path is not returned at all
whenever the lower bound of the quantifier is 0.

The engine is self-inconsistent: `*0..2` must equal `*0..0` + `*1..1` + `*2..2`
under every path mode in the standard, because a path has exactly one length and no
restrictor mentions the bounds. It does not.

Run:  python reproducers/kuzu-zero-lower-bound.py
"""
import shutil, tempfile, kuzu

path = tempfile.mkdtemp(prefix="kuzu-repro-")
shutil.rmtree(path, ignore_errors=True)
con = kuzu.Connection(kuzu.Database(path))
con.execute("CREATE NODE TABLE N(eid STRING, PRIMARY KEY(eid))")
con.execute("CREATE REL TABLE E(FROM N TO N, eid STRING)")
con.execute("CREATE (:N {eid:'x'})")
con.execute("CREATE (:N {eid:'y'})")
#  x --e1--> x   (self-loop)
#  x --e2--> y --e3--> x
for eid, s, d in [("e1", "x", "x"), ("e2", "x", "y"), ("e3", "y", "x")]:
    con.execute(f"MATCH (a:N),(b:N) WHERE a.eid='{s}' AND b.eid='{d}' "
                f"CREATE (a)-[:E {{eid:'{eid}'}}]->(b)")


def endpoints(lo, hi):
    r = con.execute(f"MATCH p=(a:N)-[:E*{lo}..{hi}]->(b:N) WHERE a.eid='x' "
                    f"RETURN b.eid AS t")
    out = {}
    while r.has_next():
        t = r.get_next()[0]
        out[t] = out.get(t, 0) + 1
    return out


print("kuzu", kuzu.__version__)
exact = {k: endpoints(k, k) for k in (0, 1, 2)}
for k, v in exact.items():
    print(f"  *{k}..{k}   {v}")

summed = {}
for v in exact.values():
    for t, c in v.items():
        summed[t] = summed.get(t, 0) + c
observed = endpoints(0, 2)

print(f"\n  *0..2 observed  {observed}")
print(f"  *0..0 + *1..1 + *2..2 = {summed}")
assert observed == summed, (
    f"\nFAILED: a bounded range is not the sum of its exact lengths.\n"
    f"  observed {observed}\n  expected {summed}\n"
    f"Every path has exactly one length and no path mode in ISO/IEC 39075 makes a\n"
    f"restrictor depend on the quantifier bounds, so these must be equal under WALK,\n"
    f"TRAIL, ACYCLIC and SIMPLE alike.")
print("\nOK -- bug appears fixed in this version.")
