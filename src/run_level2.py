"""Run the level-2 comparison: multisets of edge sequences, not endpoint pairs.

Only the projection changes. The MATCH clause is taken byte-for-byte from the query
level 1 ran, so a level-2 divergence cannot be an artefact of having asked a different
question -- it is the same question, read at higher resolution.

  python src/run_level2.py        # writes results/level2.json
"""
from __future__ import annotations
import json, os, re, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import fixtures
from engines_adapters import EngineError
from gpml_ref import match
from level2 import (admissible_edge_sequences, normalise, reference_edge_multiset)
from run_map import build_engines, pick_cypher_rendering
from capabilities import probe
from suite import CASES

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# openCypher form: project the edge ids along the bound path variable.
CY_RETURN = "RETURN x.eid AS s, [r IN relationships(p) | r.eid] AS t"
# Kuzu binds the variable-length relationship itself; rels() takes that variable.
KZ_RETURN = "RETURN x.eid AS s, rels(e) AS t"


def to_level2(query: str, engine_name: str) -> str | None:
    """Swap the projection for an edge-id projection, leaving MATCH untouched."""
    if " RETURN " not in query:
        return None
    head = query.split(" RETURN ", 1)[0]
    # The path variable must be bound for relationships(p) to exist.
    if not re.search(r"\bp\s*=", head):
        head = re.sub(r"\bMATCH\s+", "MATCH p=", head, count=1)
    if engine_name == "kuzu":
        # Kuzu needs the relationship variable named, and has no relationships().
        if not re.search(r"-\[\s*\w+\s*:", head):
            head = re.sub(r"-\[\s*:", "-[e:", head, count=1)
        head = re.sub(r"\bMATCH p=", "MATCH p=", head, count=1)
        return f"{head} {KZ_RETURN}"
    if "WITH " in head:          # the ALL SHORTEST rewrite; two MATCHes, skip
        return None
    return f"{head} {CY_RETURN}"


def main() -> int:
    workdir = os.environ.get("CF_WORKDIR", "/tmp/gpml-cf")
    os.makedirs(workdir, exist_ok=True)
    engines = build_engines(workdir)
    caps = {e.name: probe(e) for e in engines}
    print(f"engines: {[e.name for e in engines]}")

    l1 = {(c["case"], c["engine"]): c
          for c in json.load(open(os.path.join(HERE, "results", "map.json")))["cells"]}

    cells = []
    for case in CASES:
        g = fixtures.FIXTURES[case.fixture]()
        primary = fixtures.PRIMARY_LABEL[case.fixture]
        edge_label = fixtures.EDGE_LABEL[case.fixture]
        res = match(g, case.ref)
        want = reference_edge_multiset(res)
        adm = admissible_edge_sequences(res)

        for eng in engines:
            if eng.dialect != "cypher":
                continue                       # SQL/PGQ has no path object to project
            base, _ = pick_cypher_rendering(case, caps.get(eng.name))
            if base is None:
                continue
            q = to_level2(base, eng.name)
            if q is None:
                continue
            prior = l1.get((case.id, eng.name), {})
            if prior.get("verdict") not in ("CONFORMS", "DIVERGES"):
                continue                       # nothing to refine
            try:
                eng.load(g, primary, edge_label)
                ans = eng.run(q)
            except EngineError as e:
                cells.append(dict(case=case.id, engine=eng.name, level2="REJECTS",
                                  level1=prior.get("verdict"), detail=str(e)[:200],
                                  query=q))
                continue

            seqs, bad = Counter(), False
            for (_s, t), n in ans.pairs.items():
                norm = normalise(t)
                if norm is None:
                    bad = True
                    break
                seqs[norm] += n
            if bad:
                cells.append(dict(case=case.id, engine=eng.name, level2="UNAVAILABLE",
                                  level1=prior.get("verdict"),
                                  detail="edge sequence could not be normalised",
                                  query=q))
                continue

            if want is not None:
                ok = seqs == want
                detail = "" if ok else f"expected {dict(want)}, observed {dict(seqs)}"
            else:
                ok = all(k in adm for k in seqs)
                detail = "" if ok else "a returned edge sequence is not admissible"
            cells.append(dict(
                case=case.id, engine=eng.name,
                level2="CONFORMS" if ok else "DIVERGES",
                level1=prior.get("verdict"), detail=detail, query=q,
                observed={" ".join(k): v for k, v in sorted(seqs.items())},
                reference=(None if want is None
                           else {" ".join(k): v for k, v in sorted(want.items())})))

    refined = [c for c in cells
               if c["level1"] == "CONFORMS" and c["level2"] == "DIVERGES"]
    out = dict(cells=cells, refined=refined)
    dest = os.path.join(HERE, "results", "level2.json")
    json.dump(out, open(dest, "w"), indent=2)

    t = Counter(c["level2"] for c in cells)
    print(f"wrote {dest}: {len(cells)} comparable cells")
    for k, v in sorted(t.items()):
        print(f"  {k:14s} {v}")
    print(f"\n  cells that CONFORM at level 1 and DIVERGE at level 2: {len(refined)}")
    for c in refined:
        print(f"    {c['case']:30s} {c['engine']:14s} {c['detail'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
