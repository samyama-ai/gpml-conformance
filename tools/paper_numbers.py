#!/usr/bin/env python3
"""Emit every number the paper quotes as a LaTeX macro.

The paper must not contain a typed number. A typed number is a second copy of a
measurement, and the two drift -- which is how a README came to claim 5.2 s for a run
its own linked CSV recorded as 10,250.2 ms. Here the paper says \\nCells and this file
says what \\nCells is, from results/summary.json, which src/summarise.py writes from
results/map.json, which the runner writes from the engines.

Usage:  python3 tools/paper_numbers.py [--out path/to/numbers.tex]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fmt(x):
    if isinstance(x, float):
        # Always two places. A ratio printed as 0.4 next to one printed as 0.26 reads
        # as a different precision, and the reader has to decide which is rounded.
        return f"{x:.2f}"
    if isinstance(x, int) and abs(x) >= 10000:
        return f"{x:,}"
    return str(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "paper", "numbers.tex"))
    args = ap.parse_args()

    S = json.load(open(os.path.join(HERE, "results", "summary.json")))
    M = json.load(open(os.path.join(HERE, "results", "map.json")))
    MM = json.load(open(os.path.join(HERE, "results", "metamorphic.json")))
    sep = S.get("s6_separation") or {}
    agg = S["aggregates"]
    hl = agg["headline_newest_per_product"]

    acc = {}
    answer_groups = {g for g in S["by_group"]}
    for c in M["cells"]:
        if c.get("expect", "ANSWER") != "ANSWER":
            continue
        acc.setdefault(c["engine"], {}).setdefault(c["verdict"], 0)
        acc[c["engine"]][c["verdict"]] += 1

    def s2(e):
        a = acc.get(e, {})
        den = a.get("DIVERGES", 0) + a.get("REJECTS", 0)
        return a.get("DIVERGES", 0) / den if den else None

    silent = [e for e in acc if s2(e) == 1.0]
    visible = [e for e in acc if s2(e) == 0.0]

    m = {
        "nConstructs": S["n_constructs"],
        "nConstructsVone": S["constructs_by_group"].get("v1"),
        "nEngines": S["n_engines"],
        "nEnginesExternal": S["n_engines_external"],
        "nCells": S["n_cells"],
        "nRepeats": S["repeats"],
        "nProducts": len({e["name"].replace("-2026", "") for e in M["engines"]}),
        "sOne": hl["s1"],
        "sTwo": hl["s2"],
        "sOneVoneRepro": agg["v1_constructs_v1_engines"]["s1"],
        "sTwoVoneRepro": agg["v1_constructs_v1_engines"]["s2"],
        "sOneVoneAllEng": agg["v1_constructs_all_engines"]["s1"],
        "sTwoVoneAllEng": agg["v1_constructs_all_engines"]["s2"],
        "sOneAllCaseVoneEng": agg["all_constructs_v1_engines"]["s1"],
        "sTwoAllCaseVoneEng": agg["all_constructs_v1_engines"]["s2"],
        "nConforms": S["conforms"],
        "nDiverges": S["diverges"],
        "nRejects": S["rejects"],
        "nInexpressible": S["inexpressible"],
        "nDisagreements": S["disagreements"],
        "nSpecified": S["divergences_specified"],
        "nDefect": S["divergences_defect"],
        "nMultiClass": S["constructs_multi_class"],
        "nSingleClass": S["constructs_single_class"],
        "nMetamorphic": len(MM["violations"]),
        "nSilentEngines": len(silent),
        "nVisibleEngines": len(visible),
        "silentEngineList": ", ".join(sorted(silent)),
        "sepCombos": sep.get("combinations"),
        "sepClasses": sep.get("observable_classes"),
        "sepPairs": sep.get("pairs"),
        "sepSeparated": sep.get("pairs_separated"),
        "sepUnseparated": (sep.get("pairs", 0) - sep.get("pairs_separated", 0)),
        "sepGraphs": sep.get("sweep", {}).get("graphs_enumerated"),
        "sepProbes": sep.get("sweep", {}).get("pattern_probes"),
    }
    # LaTeX macro names are letters only, so a group called G1 cannot be \groupG1.
    WORD = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
            "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
    for g, v in S["by_group"].items():
        name = "".join(WORD.get(ch, ch) for ch in g)
        m[f"group{name}Constructs"] = v["constructs"]
    # S4: how many engines were askable, and how many refused every ill-formed pattern
    s4 = S["s4_wellformedness"]
    askable = [e for e, v in s4.items() if v["refused"] + v["answered"] > 0]
    allrefused = [e for e in askable if s4[e]["answered"] == 0]
    m["nWellformedAskable"] = len(askable)
    m["nWellformedEnforced"] = len(allrefused)
    m["wellformedOffenders"] = ", ".join(sorted(set(askable) - set(allrefused))) or "none"
    # S5: engines that answer two spellings of one quantifier differently
    s5 = S["s5_spelling_agreement"]
    star_key = next((k for k in next(iter(s5.values())) if "star" in k), None)
    differ = [e for e, v in s5.items() if star_key and v.get(star_key) is False]
    same = [e for e, v in s5.items() if star_key and v.get(star_key) is True]
    m["nStarDiffer"] = len(differ)
    m["nStarSame"] = len(same)
    m["nStarAsked"] = len(differ) + len(same)

    # How often the standard's own composition -- a restrictor and a selector in one
    # pattern, which Sec. 5.1 explicitly orders -- was asked and answered. A query
    # counts only if the text sent actually carried both keywords; the openCypher
    # ALL SHORTEST rewrite names no restrictor and is not the composition.
    combo_asked = combo_answered = 0
    combo_engines = set()
    for c in M["cells"]:
        if not c["case"].startswith("g1-"):
            continue
        parts = c["case"].split("-")
        if parts[2] == "walk" or "-".join(parts[3:]) == "all":
            continue
        q = c.get("query") or ""
        if not (any(k in q for k in ("TRAIL", "ACYCLIC", "SIMPLE"))
                and any(k in q for k in (" ANY", " ALL SHORTEST", "ANY SHORTEST"))):
            continue
        combo_asked += 1
        if c["verdict"] in ("CONFORMS", "DIVERGES"):
            combo_answered += 1
            combo_engines.add(c["engine"])
    m["nComboAsked"] = combo_asked
    m["nComboAnswered"] = combo_answered
    m["nComboEngines"] = len(combo_engines)

    # The per-engine table, generated for the same reason the macros are: a table of
    # eleven rows retyped into a manuscript is eleven chances for a number to drift.
    PRETTY = {"kuzu": "K\\`uzu", "duckpgq": "DuckPGQ", "neo4j": "Neo4j",
              "neo4j-2026": "Neo4j", "memgraph": "Memgraph", "apache-age": "Apache AGE",
              "arcadedb": "ArcadeDB", "falkordb": "FalkorDB", "surrealdb": "SurrealDB",
              "spanner": "Spanner Graph", "samyama-graph": "Samyama-Graph"}
    OURS, SUPERSEDED = {"samyama-graph"}, {"neo4j"}
    s4m = S["s4_wellformedness"]
    rows = []
    for e in [x["name"] for x in M["engines"]]:
        a = acc.get(e, {})
        ver = next(x["version"] for x in M["engines"] if x["name"] == e)
        ver = ver.split(" (build")[0].replace("Neo4j Kernel ", "").replace("Memgraph ", "")
        ver = ver.replace("age ", "").replace("falkordb ", "redis ")
        ver = ver.replace("cloud-spanner-emulator ", "emulator ")
        ver = ver.replace("surrealdb-", "").replace("samyama ", "")
        den = a.get("DIVERGES", 0) + a.get("REJECTS", 0)
        ans = a.get("CONFORMS", 0) + a.get("DIVERGES", 0)
        s1v = f"{a.get('DIVERGES',0)/ans:.2f}" if ans else "---"
        s2v = f"{a.get('DIVERGES',0)/den:.2f}" if den else "---"
        g4 = s4m.get(e, {})
        ask = g4.get("refused", 0) + g4.get("answered", 0)
        ill = f"{g4.get('refused',0)}/{ask}" if ask else "---"
        rows.append((e, PRETTY.get(e, e), ver, a.get("CONFORMS", 0),
                     a.get("DIVERGES", 0), a.get("REJECTS", 0),
                     a.get("INEXPRESSIBLE", 0), s1v, s2v, ill))
    tpath = os.path.join(os.path.dirname(args.out), "table_s1s2.tex")
    with open(tpath, "w") as f:
        f.write("% Generated by tools/paper_numbers.py. Do not edit.\n")
        f.write("\\begin{tabular}{@{}llrrrrrrr@{}}\n\\toprule\n")
        f.write("engine & version & conf. & div. & rej. & inexpr. & $S_1$ & $S_2$ & "
                "ill-formed \\\\\n\\midrule\n")
        for e, pretty, ver, c, d, r, i, s1v, s2v, ill in rows:
            if e in OURS:
                continue
            em = "\\itshape " if e in SUPERSEDED else ""
            f.write(f"{em}{pretty} & {em}{ver} & {em}{c} & {em}{d} & {em}{r} & "
                    f"{em}{i} & {em}{s1v} & {em}{s2v} & {em}{ill} \\\\\n")
        f.write("\\midrule\n")
        f.write(f"headline$^{{\\ast}}$ & & {hl['conforms']} & {hl['diverges']} & "
                f"{hl['rejects']} & {hl['inexpressible']} & "
                f"\\textbf{{{hl['s1']:.2f}}} & \\textbf{{{hl['s2']:.2f}}} & \\\\\n")
        f.write("\\midrule\n")
        for e, pretty, ver, c, d, r, i, s1v, s2v, ill in rows:
            if e not in OURS:
                continue
            f.write(f"\\itshape {pretty}$^{{\\ddagger}}$ & \\itshape {ver} & "
                    f"\\itshape {c} & \\itshape {d} & \\itshape {r} & "
                    f"\\itshape {i} & \\itshape {s1v} & \\itshape {s2v} & "
                    f"\\itshape {ill} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")
    print(f"wrote {tpath}: {len(rows)} rows")

    # The G1 grid, one table: every restrictor against every selector, on the bed
    # derived by tools/choose_beds.py. This is the part of the map a reader can check
    # against the standard line by line.
    SYM = {"CONFORMS": "$\\checkmark$", "DIVERGES": "$\\times$",
           "REJECTS": "!", "INEXPRESSIBLE": "--", "NONDETERMINISTIC": "?"}
    SHORT = {"kuzu": "K\\`u", "duckpgq": "DPQ", "neo4j": "N5", "neo4j-2026": "N26",
             "memgraph": "MG", "apache-age": "AGE", "arcadedb": "ARC",
             "falkordb": "FLK", "surrealdb": "SUR", "spanner": "SPN",
             "samyama-graph": "SG"}
    eng_order = [x["name"] for x in M["engines"]]
    cell = {(c["case"], c["engine"]): c["verdict"] for c in M["cells"]}
    grid_rows = []
    for r in ("walk", "trail", "acyclic", "simple"):
        for sel in ("all", "any", "all-shortest", "any-shortest"):
            cid = f"g1-fig1-{r}-{sel}"
            if (cid, eng_order[0]) not in cell:
                continue
            grid_rows.append((r.upper(), sel.replace("-", " ").upper(),
                              [SYM[cell[(cid, e)]] for e in eng_order]))
    gpath = os.path.join(os.path.dirname(args.out), "table_grid.tex")
    with open(gpath, "w") as f:
        f.write("% Generated by tools/paper_numbers.py. Do not edit.\n")
        f.write("\\begin{tabular}{@{}ll" + "c" * len(eng_order) + "@{}}\n\\toprule\n")
        f.write("mode & selector & " +
                " & ".join(SHORT.get(e, e) for e in eng_order) + " \\\\\n\\midrule\n")
        last = None
        for mode, sel, cells in grid_rows:
            if last is not None and mode != last:
                f.write("\\addlinespace[2pt]\n")
            f.write(f"{mode if mode != last else ''} & {sel} & " +
                    " & ".join(cells) + " \\\\\n")
            last = mode
        f.write("\\bottomrule\n\\end{tabular}\n")
    print(f"wrote {gpath}: {len(grid_rows)} rows")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write("% Generated by tools/paper_numbers.py. Do not edit.\n")
        f.write("% Every number the paper quotes resolves here, and here resolves to\n")
        f.write("% results/summary.json. A typed number in the manuscript is a bug.\n")
        for k, v in m.items():
            if v is None:
                continue
            f.write(f"\\newcommand{{\\{k}}}{{{fmt(v)}}}\n")
    print(f"wrote {args.out}: {sum(1 for v in m.values() if v is not None)} macros")
    return 0


if __name__ == "__main__":
    sys.exit(main())
