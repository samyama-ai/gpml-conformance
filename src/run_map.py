"""Run the conformance suite against every reachable engine and write the map.

Verdicts, as pre-registered:
  CONFORMS       the engine's answer satisfies the reference specification
  REJECTS        the engine refuses the query
  DIVERGES       the engine answers, and the answer does not satisfy the spec
  INEXPRESSIBLE  the construct has no surface syntax in that dialect
  NONDETERMINISTIC  the engine did not agree with itself across repeats
"""
from __future__ import annotations
import json, os, sys, traceback
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import fixtures
from gpml_ref import Path, match
from suite import CASES
from capabilities import probe
from engines_adapters import (AgeAdapter, BoltAdapter, DuckPGQAdapter,
                              EngineError, KuzuAdapter, SamyamaAdapter)

REPEATS = 3

# The path mode each engine's own documentation assigns to a variable-length
# pattern written with no restrictor. This is the second axis of the map: it lets a
# divergence from the ISO reference be attributed either to the *language* (the
# dialect specifies something else, and says so) or to the *implementation* (the
# engine does not do what it itself documents).
#
#   neo4j      Cypher Manual, "Pattern matching / uniqueness": a variable-length
#              relationship pattern uses relationship isomorphism -- no relationship
#              is traversed twice within one MATCH. That is TRAIL.
#   memgraph   "Differences in Cypher implementations": same relationship-uniqueness
#              rule as Neo4j.
#   apache-age openCypher-derived; inherits the relationship-uniqueness rule.
#   kuzu       "Differences between Kuzu and Neo4j": Kuzu adopts WALK semantics for
#              patterns inside MATCH, and documents the deviation explicitly.
#   duckpgq    implements SQL/PGQ, whose unrestricted path is the standard's WALK.
DECLARED_MODE = {
    "neo4j": "TRAIL",
    "memgraph": "TRAIL",
    "apache-age": "TRAIL",
    "kuzu": "WALK",
    "duckpgq": None,        # None = the dialect *is* the standard; no second axis
    "neo4j-2026": "TRAIL",
    "samyama-graph": "TRAIL",
    "samyama-graph-dev": "TRAIL",
}

def pick_cypher_rendering(case, cap):
    """Which spelling of this construct does this engine get, and what is it called?

    A hardcoded engine list used to decide this. Two engines now take the standard's
    prefixes and they disagree about the quantifier spelling, so the choice is made
    from a probe of the engine (src/capabilities.py) recorded in the map beside the
    result it explains.

    `common-dialect` is the rendering every openCypher engine can take. `gql-prefix`
    uses the standard's restrictor and selector keywords, which not every engine has
    -- it is a dialect-version difference, and since Neo4j 2026.04 it is no longer
    peculiar to one vendor.
    """
    if cap is None or not cap.takes_prefixes():
        return case.cypher, "common-dialect"
    wants_restrictor = case.ref.restrictor != "WALK"
    if wants_restrictor:
        if cap.restrictor_legacy and case.cypher_gql:
            return case.cypher_gql, "gql-prefix"
        if cap.restrictor_qpp and case.cypher_qpp:
            return case.cypher_qpp, "gql-prefix"
    else:
        if cap.selector_legacy and case.cypher_gql:
            return case.cypher_gql, "gql-prefix"
        if cap.selector_qpp and case.cypher_qpp:
            return case.cypher_qpp, "gql-prefix"
    return case.cypher, "common-dialect"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def reference_pairs(case):
    g = fixtures.FIXTURES[case.fixture]()
    res = match(g, case.ref)
    if res.deterministic:
        return res, Counter((p.start, p.end) for p in res.exact)
    return res, None


def check(res, case, observed: Counter):
    """Does the observed L1 multiset satisfy the reference specification?

    For a deterministic selector the check is multiset equality on endpoint pairs.
    For ANY / ANY SHORTEST the standard fixes only the per-partition count and the
    admissible set, so that is what is checked -- nondeterminism is never scored as
    divergence.
    """
    if res.deterministic:
        expected = Counter((p.start, p.end) for p in res.exact)
        if observed == expected:
            return True, ""
        return False, f"expected {dict(expected)}, observed {dict(observed)}"
    admissible = {(p.start, p.end) for p in res.admissible}
    for k in observed:
        if k not in admissible:
            return False, f"{k} is not an admissible endpoint pair"
    if observed != Counter(res.per_partition_count):
        return False, (f"per-endpoint-pair counts {dict(observed)} != "
                       f"{dict(res.per_partition_count)}")
    return True, ""


def declared_reference(case, engine_name):
    """The reference answer under the engine's own documented path mode.

    Only meaningful where the surface query names no restrictor. Where the case
    names one explicitly (a SQL/PGQ TRAIL/ACYCLIC/SIMPLE query) the engine is held
    to that, so the declared reference is the ISO reference.
    """
    mode = DECLARED_MODE.get(engine_name)
    if mode is None or case.ref.restrictor not in ("WALK", "TRAIL"):
        return None
    from dataclasses import replace as _replace
    from gpml_ref import UNBOUNDED
    ref = _replace(case.ref, restrictor=mode)
    if mode == "WALK" and any(s.hi == UNBOUNDED for s in ref.segments):
        if case.cypher_bound is None:
            return None      # no finite declared reference exists
        ref = _replace(ref, segments=tuple(
            _replace(s, hi=case.cypher_bound) if s.hi == UNBOUNDED else s
            for s in ref.segments))
    return ref


def build_engines(workdir):
    engines = []
    try:
        engines.append(KuzuAdapter(workdir))
    except Exception as e:
        print(f"  kuzu unavailable: {e}", file=sys.stderr)
    try:
        engines.append(DuckPGQAdapter(workdir))
    except Exception as e:
        print(f"  duckpgq unavailable: {e}", file=sys.stderr)
    for name, uri, auth in [
        ("neo4j", "bolt://localhost:7688", ("neo4j", "testpassword123")),
        # Neo4j's calendar-versioned line. 5.26 predates the GQL conformance work,
        # so measuring only it answers a question about a two-year-old release
        # rather than about the product. The paper's own limitations section names
        # this rerun as the obvious next measurement.
        ("neo4j-2026", "bolt://localhost:7690", ("neo4j", "testpassword123")),
        ("memgraph", "bolt://localhost:7689", None),
    ]:
        try:
            engines.append(BoltAdapter(name, uri, auth))
        except Exception as e:
            print(f"  {name} unavailable: {e}", file=sys.stderr)
    try:
        engines.append(AgeAdapter("host=localhost port=5433 dbname=postgres "
                                  "user=postgres password=postgres"))
    except Exception as e:
        print(f"  apache-age unavailable: {e}", file=sys.stderr)
    # The authors' own engine, measured at the release a user can install. Every
    # other row in the paper is a published release; measuring ours at a development
    # head that already carries the fixes this suite prompted would not be the same
    # comparison, and would flatter us. SAMYAMA_BIN points at the release build.
    try:
        engines.append(SamyamaAdapter(build=os.environ.get("SAMYAMA_BUILD", "v1.7.1")))
    except Exception as e:
        print(f"  samyama-graph unavailable: {e}", file=sys.stderr)
    # Optionally also measure the development head, reported separately and never in
    # a total, so the effect of the fixes is visible without entering the comparison.
    dev = os.environ.get("SAMYAMA_DEV_BIN")
    if dev and os.path.exists(dev):
        try:
            engines.append(SamyamaAdapter(binary=dev, port=8098, resp_port=6398,
                                          name="samyama-graph-dev", build="dev head"))
        except Exception as e:
            print(f"  samyama-graph-dev unavailable: {e}", file=sys.stderr)
    return engines


def main():
    workdir = os.environ.get("CF_WORKDIR", "/tmp/gpml-cf")
    os.makedirs(workdir, exist_ok=True)
    engines = build_engines(workdir)
    print(f"engines: {[e.name for e in engines]}")

    # Ask each engine which spelling of the standard's path prefixes it parses,
    # before measuring anything, and keep the answer in the map.
    caps = {e.name: probe(e) for e in engines}
    for n, c in caps.items():
        if c.takes_prefixes():
            print(f"  {n}: GQL prefixes {c.as_dict()}")

    cells = []
    for case in CASES:
        res, _ = reference_pairs(case)
        g = fixtures.FIXTURES[case.fixture]()
        primary = fixtures.PRIMARY_LABEL[case.fixture]
        edge_label = fixtures.EDGE_LABEL[case.fixture]
        for eng in engines:
            if eng.dialect == "cypher":
                query, surface = pick_cypher_rendering(case, caps.get(eng.name))
            else:
                query = case.pgq
                surface = "common-dialect"
            if query is None:
                cells.append(dict(case=case.id, engine=eng.name, verdict="INEXPRESSIBLE",
                                  surface=surface,
                                  detail="no surface syntax in this dialect"))
                continue
            try:
                eng.load(g, primary, edge_label)
            except Exception as e:
                cells.append(dict(case=case.id, engine=eng.name, verdict="LOAD_FAILED", surface=surface,
                                  detail=str(e)[:300], query=query))
                continue
            answers, diags, err = [], None, None
            for _ in range(REPEATS):
                try:
                    a = eng.run(query)
                    answers.append(a.pairs)
                    diags = a.diagnostics
                except EngineError as e:
                    err = str(e)[:300]
                    break
            if err is not None:
                cells.append(dict(case=case.id, engine=eng.name, verdict="REJECTS", surface=surface,
                                  detail=err, query=query))
                continue
            if any(a != answers[0] for a in answers[1:]):
                cells.append(dict(case=case.id, engine=eng.name,
                                  verdict="NONDETERMINISTIC", surface=surface,
                                  detail=[dict(a) for a in answers], query=query))
                continue
            ok, why = check(res, case, answers[0])
            dref = declared_reference(case, eng.name)
            if dref is None:
                declared_verdict, declared_detail = None, ""
            else:
                dres = match(fixtures.FIXTURES[case.fixture](), dref)
                dok, dwhy = check(dres, case, answers[0])
                declared_verdict = "CONFORMS" if dok else "DIVERGES"
                declared_detail = dwhy
            cells.append(dict(
                # A list of what the engine said alongside the answer; None means
                # this adapter has no way to ask, which is not the same fact as an
                # engine that was asked and said nothing.
                diagnostics=diags,
                diagnostics_supported=(diags is not None),
                declared_mode=DECLARED_MODE.get(eng.name),
                verdict_vs_declared=declared_verdict,
                detail_vs_declared=declared_detail,
                case=case.id, engine=eng.name, surface=surface,
                verdict="CONFORMS" if ok else "DIVERGES",
                detail=why, query=query,
                observed={f"{k[0]}->{k[1]}": v for k, v in sorted(answers[0].items())},
                reference=(None if not res.deterministic else
                           {f"{p.start}->{p.end}": c for p, c in
                            _ref_counter(res).items()}),
            ))

    out = dict(
        engines=[dict(name=e.name, dialect=e.dialect, version=str(e.version),
                      gql_syntax=caps[e.name].as_dict())
                 for e in engines],
        repeats=REPEATS,
        cells=cells,
    )
    dest = os.path.join(HERE, "results", "map.json")
    with open(dest, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {dest}: {len(cells)} cells")
    tally = Counter(c["verdict"] for c in cells)
    for k, v in sorted(tally.items()):
        print(f"  {k:18s} {v}")


def _ref_counter(res):
    c = Counter()
    for p in res.exact:
        c[p] = c.get(p, 0)
    out = Counter()
    for p in res.exact:
        out[type("K", (), {"start": p.start, "end": p.end})()] = 0
    # simple endpoint counter
    e = Counter()
    for p in res.exact:
        e[p] += 1
    agg = Counter()
    for p, n in e.items():
        agg[_EP(p.start, p.end)] += n
    return agg


class _EP:
    __slots__ = ("start", "end")

    def __init__(self, s, e):
        self.start, self.end = s, e

    def __hash__(self):
        return hash((self.start, self.end))

    def __eq__(self, o):
        return (self.start, self.end) == (o.start, o.end)


if __name__ == "__main__":
    main()
