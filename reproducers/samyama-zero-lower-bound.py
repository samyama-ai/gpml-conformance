"""Minimal reproducer: Samyama-Graph 1.7.1 collapses `*0..n` to distinct endpoints.

With a lower bound of zero, a variable-length pattern returns one row per reachable
end node instead of one row per path. Parallel edges are two distinct paths, and the
engine returns one.

The engine is self-inconsistent about it: `*1..1` on the same graph does return both
parallel edges, and `*0..2` must equal `*0..0` + `*1..1` + `*2..2` under every path
mode in ISO/IEC 39075, because no restrictor mentions the quantifier bounds.

Run against a server started with:
  samyama --port 6399 --http-port 8099 --ephemeral
"""
import json
import urllib.request

BASE = "http://localhost:8099/api/query"


def q(query):
    req = urllib.request.Request(
        BASE, data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


print("engine", q("RETURN 1")["engine_version"])

#  a =e1,e2=> b --e3--> c --e4--> a   (two parallel edges a->b)
for n in ("a", "b", "c"):
    q(f'CREATE (x:N {{eid: "{n}"}})')
for eid, s, d in [("e1", "a", "b"), ("e2", "a", "b"), ("e3", "b", "c"), ("e4", "c", "a")]:
    q(f'MATCH (x),(y) WHERE x.eid="{s}" AND y.eid="{d}" '
      f'CREATE (x)-[:E {{eid:"{eid}"}}]->(y)')


def hops(lo, hi):
    rows = q(f'MATCH p=(x:N)-[:E*{lo}..{hi}]->(y:N) WHERE x.eid="a" '
             f'RETURN y.eid')["records"]
    out = {}
    for (t,) in rows:
        out[t] = out.get(t, 0) + 1
    return out


exact = {k: hops(k, k) for k in (0, 1, 2)}
for k, v in exact.items():
    print(f"  *{k}..{k}   {v}")

summed = {}
for v in exact.values():
    for t, c in v.items():
        summed[t] = summed.get(t, 0) + c
observed = hops(0, 2)

print(f"\n  *0..2 observed  {observed}")
print(f"  *0..0 + *1..1 + *2..2 = {summed}")
assert observed == summed, (
    f"\nFAILED: a bounded range is not the sum of its exact lengths.\n"
    f"  observed {observed}\n  expected {summed}\n"
    f"*1..1 returns both parallel edges; *0..2 returns one row per end node.")
print("\nOK -- bug appears fixed in this version.")
