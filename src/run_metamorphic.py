"""Run the metamorphic relations against every engine, on every fixture."""
from __future__ import annotations
import json, os, sys
from collections import Counter
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(__file__))
import fixtures
from engines_adapters import EngineError
from metamorphic import check_engine
from run_map import build_engines

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = [(lo, hi) for hi in range(0, 5) for lo in range(0, hi + 1)]

CY = ("MATCH p=(x:{L})-[:{E}*{lo}..{hi}]->(y:{L}) WHERE x.eid='{s}' "
      "RETURN x.eid AS s, y.eid AS t")
PG = ("FROM GRAPH_TABLE(g MATCH (x:{L})-[e:{E}]->{{{lo},{hi}}}(y:{L}) "
      "WHERE x.eid='{s}' COLUMNS (x.eid AS s, y.eid AS t)) SELECT s, t")

STARTS = {"micro": "a", "cycle2": "m", "loop": "x", "single": "u",
          "tagged": "p", "fig1": "a6"}


def main():
    workdir = os.environ.get("CF_WORKDIR", "/tmp/gpml-cf")
    os.makedirs(workdir, exist_ok=True)
    engines = build_engines(workdir)
    out = []
    # A query that errors cannot violate a relation: check_engine simply skips any
    # relation that needs it, so a crash lowers an engine's violation count instead of
    # raising it. Record every refusal, so the counts can be read as the lower bounds
    # they are rather than taken for complete (issue #4).
    dropped = []
    for fx, start in STARTS.items():
        g = fixtures.FIXTURES[fx]()
        L = fixtures.PRIMARY_LABEL[fx]
        E = fixtures.EDGE_LABEL[fx]
        for eng in engines:
            eng.load(g, L, E)
            tmpl = CY if eng.dialect == "cypher" else PG

            def run(lo, hi, _e=eng, _t=tmpl, _fx=fx):
                q = _t.format(L=L, E=E, lo=lo, hi=hi, s=start)
                try:
                    return _e.run(q).pairs
                except EngineError as e:
                    dropped.append(dict(engine=_e.name, fixture=_fx, lo=lo, hi=hi,
                                        query=q, error=str(e)[:300]))
                    return None

            def _str_keys(d):
                return {f"{k[0]}->{k[1]}": v for k, v in sorted(d.items())}

            for v in check_engine(run, PAIRS, max_len=4):
                d = asdict(v)
                d["left_answer"] = _str_keys(v.left_answer)
                d["right_answer"] = _str_keys(v.right_answer)
                d.update(fixture=fx, engine=eng.name, start=start)
                out.append(d)
                print(f"[{eng.name}/{fx}] {v.relation}: {v.left} vs {v.right}")
                print(f"    {v.left_answer}  vs  {v.right_answer}")
    dest = os.path.join(HERE, "results", "metamorphic.json")
    with open(dest, "w") as f:
        json.dump(dict(pairs=PAIRS, violations=out, dropped=dropped), f, indent=2)
    print(f"\nwrote {dest}: {len(out)} violation(s)")
    per = Counter(v["engine"] for v in out)
    for k, n in per.items():
        print(f"  {k:12s} {n}")
    if dropped:
        print(f"{len(dropped)} query/queries errored and were skipped; "
              f"every count above is a lower bound:")
        for k, n in Counter(d["engine"] for d in dropped).items():
            print(f"  {k:12s} {n} dropped")
    else:
        print("no query errored: no relation was skipped")


if __name__ == "__main__":
    main()
