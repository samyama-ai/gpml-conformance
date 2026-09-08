# Post-publication re-measurement of one engine

This file records a measurement taken **after** `results/` was generated. It does
not change any number in `results/`, `RESULTS.md`, or the paper. Those record what
the engines computed on 2026-09-07 and are left alone.

## What prompted it

`RESULTS.md` discloses that the engine developed by the authors scored worst of the
six measured: 8 constructs conforming, 4 diverging, 5 inexpressible, silence ratio
1.00, and 24 metamorphic violations. The root cause — a quantifier with lower bound 0
collapsing the path multiset to one row per reachable end node — was filed publicly as
[samyama-graph#1140](https://github.com/samyama-ai/samyama-graph/issues/1140).

That issue and three others were fixed on 2026-09-08:

| issue | what shipped | PR |
|---|---|---|
| #1140 | lower bound 0 no longer collapses the multiset | samyama-graph#1144 |
| #1141 | GQL path restrictors (WALK/TRAIL/ACYCLIC/SIMPLE) and selectors (ALL/ANY/ALL SHORTEST/ANY SHORTEST) | samyama-graph#1145 |
| #1143 | `CALL db.checkIntegrity()` | samyama-graph#1146 |
| #1142 | three metamorphic relations as a CI gate | samyama-graph#1147 |

## The re-measurement

Build: `samyama-graph` at commit `3cb2461`, reporting version string `1.7.1`. This is
an **unreleased build**; no released version of the engine scores what follows.

Method: `src/run_map.py` and `src/run_metamorphic.py` unchanged. The five external
engines were not installed on the measuring host, so only our column was produced;
their cells are untouched in `results/`. The five constructs previously scored
INEXPRESSIBLE were re-asked using the surface syntax added by samyama-graph#1145 and
scored with the suite's own `check()` against `src/gpml_ref.py`, not by inspection.

| metric | 2026-09-07 (paper) | 2026-09-08 (this build) |
|---|---|---|
| constructs conforming | 8 / 17 | **17 / 17** |
| diverging | 4 | 0 |
| inexpressible | 5 | 0 |
| silence ratio | 1.00 | not defined (no divergences) |
| metamorphic violations | 24 | 0 |

The two divergences that survived the fixes under the suite's *stored* Cypher text
(`mode-walk-bounded`, `walk-revisits-same-edge`) were already scored CONFORMS against
the engine's declared TRAIL mode; both are the documented openCypher
relationship-isomorphism difference. Asked explicitly in `WALK` mode they return the
standard's answer.

## What this does not establish

- One engine, measured by its own authors, on an unreleased build. The cross-engine
  numbers this artifact exists to report are unaffected and unrepeated.
- The suite still stores **one** `cypher` string per case, shared by every
  openCypher-family engine. Constructs that now have samyama surface syntax cannot be
  expressed in the suite without per-engine syntax overrides, so those five cells
  remain INEXPRESSIBLE in `results/map.json` and were scored here out of band. Tracked
  as an issue on this repository.
