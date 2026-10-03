"""Minimal reproducer: Grafeo 0.5.40 is OOM-killed by an ill-formed unbounded pattern.

GPML (Deutsch et al., Sec. 5) requires that every unbounded quantifier lie in the scope
of a restrictor or a selector, so that the answer is finite. `WALK` with selector `ALL`
and an unbounded quantifier is therefore ill-formed, and a conforming engine refuses it.

Grafeo accepts it and tries to enumerate it. On a three-node, four-edge graph the server
process grows without bound and is killed; with a 3 GB container limit it dies in under
two minutes, every time.

  MATCH WALK (x:N)-[:E*0..]->(y:N) WHERE x.name='a' RETURN x.eid, y.eid

Two neighbouring queries behave differently, which localises it:

  MATCH TRAIL (x:N)-[:E*0..]->(y:N) ...   answers correctly (the restrictor bounds it)
  MATCH p=(x:N)-[:E*]->(y:N) ...          returns HTTP 408 after a 30s query timeout

So the engine has a query timeout and it does not save it here: the explicit `WALK`
path takes a different route that allocates faster than the timeout fires.

Reproduce:
  docker run -d --name grafeo-oom --memory=3g -p 7475:7474 grafeo/grafeo-server:latest
  python reproducers/grafeo-walk-unbounded-oom.py
  docker inspect grafeo-oom --format '{{.State.OOMKilled}} {{.State.ExitCode}}'
      -> true 137

Observed 3 times out of 3 on Grafeo 0.5.40 (image digest in results/map.json).
"""
import sys
import time

import requests

BASE = "http://localhost:7475"
NODES = [("a", "a"), ("b", "b"), ("c", "c")]
EDGES = [("e1", "a", "b"), ("e2", "a", "b"), ("e3", "b", "c"), ("e4", "c", "a")]
ILL_FORMED = ("MATCH WALK (x:N)-[:E*0..]->(y:N) WHERE x.name='a' "
              "RETURN x.eid AS s, y.eid AS t")


def q(text, timeout=120):
    r = requests.post(f"{BASE}/query", json={"query": text}, timeout=timeout)
    return r.status_code, r.text[:200]


def main() -> int:
    q("MATCH (n) DETACH DELETE n")
    for eid, name in NODES:
        q(f"CREATE (:N {{eid:'{eid}', name:'{name}'}})")
    for eid, s, d in EDGES:
        q(f"MATCH (a),(b) WHERE a.eid='{s}' AND b.eid='{d}' "
          f"CREATE (a)-[:E {{eid:'{eid}'}}]->(b)")

    print("control  TRAIL *0.. :", q("MATCH TRAIL (x:N)-[:E*0..]->(y:N) "
                                     "WHERE x.name='a' RETURN x.eid AS s, y.eid AS t"))
    print("control  bare *     :", q("MATCH p=(x:N)-[:E*]->(y:N) WHERE x.name='a' "
                                     "RETURN x.eid AS s, y.eid AS t"))
    print("ill-formed WALK *0..: ", end="", flush=True)
    t0 = time.time()
    try:
        print(q(ILL_FORMED))
        print("the server survived; it did not on 3 of 3 earlier runs")
        return 1
    except requests.exceptions.ConnectionError as ex:
        print(f"server died after {time.time() - t0:.0f}s -- {type(ex).__name__}")
        print("check: docker inspect <container> --format "
              "'{{.State.OOMKilled}} {{.State.ExitCode}}'")
        return 0


if __name__ == "__main__":
    sys.exit(main())
