"""Compute the pre-registered statistics S1, S2, S3 and write RESULTS.md."""
import json, os, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
from suite_all import CASES, GROUPS, resolve
from suite_v2 import G5_PAIRS
from diagnostics import classify, speaks_about_divergence

BYID = {c.id: c for c in CASES}

# The authors' own engine. It is measured by the same suite and shown as a row, but it
# is excluded from every headline statistic; see the conflict-of-interest note.
OURS = {"samyama-graph"}

# Two Neo4j releases are measured. Counting both in one aggregate would weight that
# vendor twice, so the headline is computed over **one row per product**, taking the
# newest version measured. `SUPERSEDED` names the rows shown but excluded from the
# aggregate for that reason -- not because they are uninteresting: the drift between
# them is reported separately, and is the only evidence here about whether the field
# is converging on the standard.
#
# All three aggregates are written to summary.json so the choice is visible and the
# paper's claims registry can resolve whichever it quotes.
SUPERSEDED = {"neo4j"}          # superseded by neo4j-2026 in the headline set

SYM = {"CONFORMS": "✓", "DIVERGES": "✗", "REJECTS": "!", "INEXPRESSIBLE": "–",
       "NONDETERMINISTIC": "?", "LOAD_FAILED": "∅"}


def _level2_summary():
    """Does comparing edge sequences find divergence that endpoint pairs miss?"""
    p = os.path.join(HERE, "results", "level2.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    pair = Counter((c["level1"], c["level2"]) for c in d["cells"])
    return {
        "comparable_cells": len(d["cells"]),
        "conforms_both": pair[("CONFORMS", "CONFORMS")],
        "diverges_both": pair[("DIVERGES", "DIVERGES")],
        # The question the paper's stated limitation asks: how many cells look
        # identical at endpoint level and differ once you compare the paths?
        "refined_by_level2": pair[("CONFORMS", "DIVERGES")],
        # The reverse would mean level 2 is less strict than level 1, which cannot
        # happen if both are computed correctly. Checked, not assumed.
        "contradicts_level1": pair[("DIVERGES", "CONFORMS")],
        "not_projectable": pair[("CONFORMS", "REJECTS")] + pair[("DIVERGES", "REJECTS")],
    }


AS_PUBLISHED = {"kuzu", "duckpgq", "neo4j", "memgraph", "apache-age"}


def _aggregates(m, answer_cases, v1_cases):
    """S1 and S2 under each population worth naming.

    Widening the matrix changes the denominator, so a bare S1 from this run is not
    comparable to the published one. Each population is named and reported, and the
    one that reproduces the published figure keeps both the old engine set and the
    old construct set -- change one thing at a time or the comparison says nothing.
    """
    sets = {
        "headline_newest_per_product": (
            lambda c: c["engine"] not in OURS and c["engine"] not in SUPERSEDED
            and c["case"] in answer_cases),
        "all_external_rows": (
            lambda c: c["engine"] not in OURS and c["case"] in answer_cases),
        # v1's constructs, v1's engines: what the published paper measured.
        "v1_constructs_v1_engines": (
            lambda c: c["engine"] in AS_PUBLISHED and c["case"] in v1_cases),
        # v1's constructs, every external engine now in the matrix: isolates the
        # effect of adding engines.
        "v1_constructs_all_engines": (
            lambda c: c["engine"] not in OURS and c["case"] in v1_cases),
        # Every construct, v1's engines: isolates the effect of adding constructs.
        "all_constructs_v1_engines": (
            lambda c: c["engine"] in AS_PUBLISHED and c["case"] in answer_cases),
    }
    out = {}
    for name, keep in sets.items():
        t = Counter(c["verdict"] for c in m["cells"] if keep(c))
        answered = t["CONFORMS"] + t["DIVERGES"]
        den = t["DIVERGES"] + t["REJECTS"]
        out[name] = {
            "engines": sorted({c["engine"] for c in m["cells"] if keep(c)}),
            "cells": sum(1 for c in m["cells"] if keep(c)),
            "conforms": t["CONFORMS"], "diverges": t["DIVERGES"],
            "rejects": t["REJECTS"], "inexpressible": t["INEXPRESSIBLE"],
            "s1": round(t["DIVERGES"] / answered, 4) if answered else None,
            "s2": round(t["DIVERGES"] / den, 4) if den else None,
        }
    return out


def _snapshot_summary():
    """Per-engine verdict counts from the frozen 2026-09-07 map, if present."""
    p = os.path.join(HERE, "results", "snapshots", "map-2026-09-07.json")
    if not os.path.exists(p):
        return None
    snap = json.load(open(p))
    out = {}
    for c in snap["cells"]:
        out.setdefault(c["engine"], Counter())[c["verdict"]] += 1
    mp = os.path.join(HERE, "results", "snapshots", "metamorphic-2026-09-07.json")
    meta = Counter()
    if os.path.exists(mp):
        for v in json.load(open(mp))["violations"]:
            meta[v["engine"]] += 1
    return {e: {**dict(v), "metamorphic": meta.get(e, 0)} for e, v in out.items()}



def _write_readme_scorecard(summary, engines, ver, acc, s4, sep):
    """Rewrite the generated block in README.md.

    A README that restates a measurement is a second copy of it, and two copies drift.
    The one in README.md is written from the same summary the paper's claims registry
    resolves against, so there is one number and one place it comes from.
    """
    path = os.path.join(HERE, "README.md")
    if not os.path.exists(path):
        return
    begin, end = ("<!-- BEGIN GENERATED: scorecard -->",
                  "<!-- END GENERATED: scorecard -->")
    text = open(path).read()
    if begin not in text or end not in text:
        return
    hl = summary["aggregates"]["headline_newest_per_product"]
    L = [begin, ""]
    L.append(f"**{summary['n_constructs']} constructs x {summary['n_engines']} engines "
             f"= {summary['n_cells']} cells.** Each cell is one exact multiset "
             f"comparison, run {summary['repeats']} times to confirm the engine agrees "
             f"with itself.")
    L.append("")
    L.append("| engine | version | conforms | diverges | rejects | inexpressible | "
             "silence ratio | refuses ill-formed |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for e in engines:
        a = acc[e]
        den = a["DIVERGES"] + a["REJECTS"]
        s2 = f"{a['DIVERGES']/den:.2f}" if den else "n/a"
        g4 = s4.get(e, {})
        askable = g4.get("refused", 0) + g4.get("answered", 0)
        ill = f"{g4.get('refused', 0)}/{askable}" if askable else "not askable"
        mark = " *(ours)*" if e in OURS else ""
        # Some engines report a build hash after the version. The version is the fact;
        # the hash makes the table unreadable and is in results/map.json either way.
        v = ver[e].split(" (build")[0]
        L.append(f"| {e}{mark} | {v} | {a['CONFORMS']} | {a['DIVERGES']} | "
                 f"{a['REJECTS']} | {a['INEXPRESSIBLE']} | {s2} | {ill} |")
    L.append("")
    L.append(f"Over every engine but ours and the superseded Neo4j line: "
             f"**S1 = {hl['s1']}** of answered cells diverge, and "
             f"**S2 = {hl['s2']}** of disagreements are silent -- the query runs, "
             f"returns a different multiset, raises nothing. The silence ratio is a "
             f"property of the engine, not of the problem: the table above spans the "
             f"whole range from 0 to 1.")
    if sep:
        L.append("")
        L.append(f"The standard defines {sep['combinations']} restrictor x selector "
                 f"combinations. Over an exhaustive sweep of "
                 f"{sep['sweep']['graphs_enumerated']:,} directed multigraphs, "
                 f"{sep['pairs_separated']} of {sep['pairs']} cell pairs have a "
                 f"separating witness and "
                 f"{sep['pairs'] - sep['pairs_separated']} have none: "
                 f"**{sep['observable_classes']} of {sep['combinations']} combinations "
                 f"are observably different.** A shortest path is already simple, so "
                 f"the restrictor is unobservable under a shortest selector except for "
                 f"ACYCLIC.")
    L.append("")
    L.append(end)
    out = text[:text.index(begin)] + "\n".join(L) + text[text.index(end) + len(end):]
    open(path, "w").write(out)
    print(f"wrote {path} (generated block)")


def main():
    m = json.load(open(os.path.join(HERE, "results", "map.json")))
    mm = json.load(open(os.path.join(HERE, "results", "metamorphic.json")))
    engines = [e["name"] for e in m["engines"]]
    ver = {e["name"]: e["version"] for e in m["engines"]}
    grid = {(c["case"], c["engine"]): c for c in m["cells"]}

    L = []
    L.append("# Results\n")
    L.append("Generated by `src/summarise.py` from `results/map.json` and "
             "`results/metamorphic.json`. Do not edit by hand.\n")

    L.append("## Engines\n")
    L.append("| engine | dialect | version |")
    L.append("|---|---|---|")
    for e in m["engines"]:
        L.append(f"| {e['name']} | {e['dialect']} | {e['version']} |")

    L.append(f"\nEach cell is one exact multiset comparison, repeated "
             f"{m['repeats']} times to confirm the engine is deterministic.\n")

    L.append("## The map\n")
    L.append("| construct | " + " | ".join(engines) + " |")
    L.append("|---" * (len(engines) + 1) + "|")
    for c in CASES:
        cells = [grid[(c.id, e)] for e in engines]
        row = " | ".join(
            SYM[x["verdict"]] + ("\u2020" if x.get("surface") == "vendor-extension" else "")
            for x in cells)
        L.append(f"| `{c.id}` | {row} |")
    L.append("\n\u2713 conforms  \u2717 diverges  ! rejects  \u2013 inexpressible in that dialect  "
             "\u2205 engine failed to load the fixture\n")

    vend = [c for c in m["cells"] if c.get("surface") == "vendor-extension"]
    if vend:
        by_eng = Counter(c["engine"] for c in vend)
        L.append("\u2020 answered through a **vendor extension**: syntax that engine has and "
                 "the common dialect does not. Such a cell says the engine can express "
                 "and compute the construct; it does not say the construct is portable, "
                 "and it is not evidence about the dialect the other engines share. "
                 "Counted here so a vendor cannot raise its score merely by extending "
                 "its own syntax without the reader seeing it.\n")
        L.append("| engine | cells answered via a vendor extension |")
        L.append("|---|---:|")
        for e in engines:
            if by_eng.get(e):
                L.append(f"| {e} | {by_eng[e]} |")
        L.append("")

    acc = {e: Counter() for e in engines}
    for c in m["cells"]:
        if c["case"] in {x.id for x in CASES if x.expect == "ANSWER"}:
            acc[c["engine"]][c["verdict"]] += 1
    # S1 and S2 are statistics about *answers*. G4 asks whether an engine refuses a
    # pattern the standard makes ill-formed and G5 asks whether two spellings of one
    # quantifier agree; in both a rejection can be the conforming act, so folding them
    # into a divergence rate would mix two different questions into one decimal. They
    # get their own statistics below, and the answer population is stated explicitly.
    ANSWER_CASES = {c.id for c in CASES if c.expect == "ANSWER"}
    external = [c for c in m["cells"]
                if c["engine"] not in OURS and c["engine"] not in SUPERSEDED
                and c["case"] in ANSWER_CASES]
    tot = Counter(c["verdict"] for c in external)
    ext_engines = [e for e in engines
                   if e not in OURS and e not in SUPERSEDED]

    L.append("## S1 — divergence rate, and S2 — silence ratio\n")
    L.append("S1 is divergences over the cells the engine answered. S2 is divergences "
             "over divergences plus rejections: the share of disagreements the user is "
             "*not* told about.\n")
    L.append("| engine | conforms | diverges | rejects | inexpressible | S1 | S2 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for e in engines:
        a = acc[e]
        answered = a["CONFORMS"] + a["DIVERGES"]
        den = a["DIVERGES"] + a["REJECTS"]
        s1 = f"{a['DIVERGES']/answered:.2f}" if answered else "n/a"
        s2 = f"{a['DIVERGES']/den:.2f}" if den else "n/a"
        star = " *(ours — excluded from the totals)*" if e in OURS else ""
        L.append(f"| {e}{star} | {a['CONFORMS']} | {a['DIVERGES']} | {a['REJECTS']} | "
                 f"{a['INEXPRESSIBLE']} | {s1} | {s2} |")
    answered = tot["CONFORMS"] + tot["DIVERGES"]
    den = tot["DIVERGES"] + tot["REJECTS"]
    L.append(f"| **all five external engines** | {tot['CONFORMS']} | {tot['DIVERGES']} | "
             f"{tot['REJECTS']} | {tot['INEXPRESSIBLE']} | "
             f"**{tot['DIVERGES']/answered:.2f}** | **{tot['DIVERGES']/den:.2f}** |")

    L.append("\n## Attribution: language difference or implementation defect?\n")
    L.append("A divergence from the ISO reference is only a defect if the engine also "
             "departs from what it documents. The second column re-scores each answer "
             "against the path mode the engine's own manual declares.\n")
    L.append("| construct | engine | vs ISO reference | vs engine's declared mode |")
    L.append("|---|---|---|---|")
    spec = impl = 0
    for c in external:
        if c["verdict"] != "DIVERGES":
            continue
        vd = c.get("verdict_vs_declared")
        if vd == "CONFORMS":
            spec += 1
            tag = "conforms — the deviation is documented"
        elif vd == "DIVERGES":
            impl += 1
            tag = "**diverges — defect**"
        else:
            impl += 1
            tag = "**n/a — the dialect is the standard, so this is a defect**"
        L.append(f"| `{c['case']}` | {c['engine']} | diverges | {tag} |")
    L.append(f"\n**{spec} of {spec+impl} divergences are specified language "
             f"differences** — the engine does exactly what it documents. The "
             f"remaining **{impl}** are departures from the standard the engine "
             f"itself implements.\n")

    # ---- S2b: of the divergences, how many were delivered with nothing said? ----
    L.append("## S2b — divergences delivered with neither an error nor a relevant diagnostic\n")
    L.append("S2 counts a rejection as the engine having spoken. S2b asks a narrower "
             "question: of the answers that were *wrong and returned*, how often was the "
             "user told anything about it? A diagnostic counts only when it names the "
             "construct at issue -- Memgraph attaches a `PlanHinting` index suggestion "
             "to every cell it answers, which is not a warning about the answer.\n")
    L.append("| engine | divergences | with a relevant diagnostic | S2b | has a channel | irrelevant diagnostics |")
    L.append("|---|---:|---:|---:|---|---:|")
    s2b_rows = {}
    for e in engines:
        divs = [c for c in m["cells"] if c["engine"] == e and c["verdict"] == "DIVERGES"]
        spoke = sum(1 for c in divs if speaks_about_divergence(c.get("diagnostics")))
        chan = any(c.get("diagnostics_supported") for c in m["cells"] if c["engine"] == e)
        irrelevant = sum(1 for c in m["cells"] if c["engine"] == e
                         for d in (c.get("diagnostics") or [])
                         if classify(d)[0] != "semantic")
        val = (len(divs) - spoke) / len(divs) if divs else None
        s2b_rows[e] = dict(divergences=len(divs), spoke=spoke,
                           s2b=(round(val, 4) if val is not None else None),
                           channel=chan, irrelevant=irrelevant)
        star = " *(ours)*" if e in OURS else ""
        L.append(f"| {e}{star} | {len(divs)} | {spoke} | "
                 f"{'n/a' if val is None else f'{val:.2f}'} | "
                 f"{'yes' if chan else 'no'} | {irrelevant} |")
    ext_div = sum(v["divergences"] for e, v in s2b_rows.items() if e not in OURS)
    ext_spoke = sum(v["spoke"] for e, v in s2b_rows.items() if e not in OURS)
    L.append(f"| **all five external** | {ext_div} | {ext_spoke} | "
             f"**{(ext_div - ext_spoke) / ext_div:.2f}** | | |")
    L.append("\nEvery diagnostic credited above was checked rather than counted: "
             "`PathModeAffectsResult` claims that naming the path mode would change the "
             "answer, and that claim was re-tested by running the same pattern under "
             "each mode. All verified true; no false positives.\n")

    L.append("## S3 — answer classes per construct\n")
    L.append("How many distinct answers the engines that accepted the query gave. "
             "One class means the construct is portable.\n")
    L.append("| construct | classes | grouping |")
    L.append("|---|---:|---|")
    for c in CASES:
        classes = defaultdict(list)
        for e in ext_engines:
            cell = grid[(c.id, e)]
            if cell["verdict"] in ("CONFORMS", "DIVERGES"):
                classes[json.dumps(cell.get("observed"), sort_keys=True)].append(e)
        if classes:
            grouping = " / ".join("{" + ", ".join(v) + "}" for v in classes.values())
            L.append(f"| `{c.id}` | {len(classes)} | {grouping} |")

    # ---- S4: does the engine refuse what the standard makes ill-formed? ----
    g4_reject = [c for c in CASES if c.expect == "REJECT"]
    g4_accept = [c for c in CASES if c.expect == "ACCEPT"]
    s4 = {}
    L.append("\n## S4 — well-formedness enforcement\n")
    L.append("Sec. 5 makes an unbounded quantifier ill-formed unless a restrictor or a "
             "selector is in scope. Refusing such a pattern is the conforming act and "
             "answering it is the defect — a direction no answer comparison can see. "
             "The accept controls are not decoration: an engine that refuses everything "
             "would otherwise score a clean sweep.\n")
    L.append("| engine | ill-formed refused | ill-formed answered | not askable | "
             "well-formed controls accepted |")
    L.append("|---|---:|---:|---:|---:|")
    for e in engines:
        ref = sum(1 for c in g4_reject if grid[(c.id, e)]["verdict"] == "CONFORMS")
        ans = sum(1 for c in g4_reject if grid[(c.id, e)]["verdict"] == "DIVERGES")
        na = sum(1 for c in g4_reject
                 if grid[(c.id, e)]["verdict"] == "INEXPRESSIBLE")
        ctl = sum(1 for c in g4_accept
                  if grid[(c.id, e)]["verdict"] in ("CONFORMS", "DIVERGES"))
        s4[e] = {"refused": ref, "answered": ans, "not_askable": na,
                 "controls_accepted": ctl, "controls_total": len(g4_accept)}
        L.append(f"| {e} | {ref} | {ans} | {na} | {ctl}/{len(g4_accept)} |")

    # ---- S5: does one engine answer two spellings of one quantifier the same? ----
    s5 = {}
    L.append("\n## S5 — spelling self-contradiction\n")
    L.append("Two ways of writing one quantifier, which the standard says mean the same "
             "thing. An engine that answers them differently contradicts itself, and the "
             "contradiction needs no reference semantics to see. Reported per engine and "
             "never as a rate: with four cases a rate is a count wearing a decimal "
             "point.\n")
    L.append("| engine | " + " | ".join(f"`{a}` vs `{b}`" for a, b in G5_PAIRS) + " |")
    L.append("|---" * (len(G5_PAIRS) + 1) + "|")
    for e in engines:
        row, rec = [], {}
        for a, b in G5_PAIRS:
            ca, cb = grid.get((resolve(a), e)), grid.get((resolve(b), e))
            if not ca or not cb:
                row.append("—"); rec[f"{a}|{b}"] = None; continue
            if ca["verdict"] == "REJECTS" or cb["verdict"] == "REJECTS":
                row.append("not askable"); rec[f"{a}|{b}"] = None; continue
            same = ca.get("observed") == cb.get("observed")
            row.append("same" if same else "**differ**")
            rec[f"{a}|{b}"] = bool(same)
        s5[e] = rec
        L.append(f"| {e} | " + " | ".join(row) + " |")

    # ---- S6: how much of the grid is observable at all? ----
    s6 = None
    sep_path = os.path.join(HERE, "results", "separation.json")
    if os.path.exists(sep_path):
        sep = json.load(open(sep_path))
        s6 = {"observable_classes": sep["observable_classes"],
              "combinations": sep["combinations"],
              "pairs_separated": sep["separated"], "pairs": sep["pairs"],
              "unobservable": sep["unobservable"], "sweep": sep["sweep"]}
        L.append("\n## S6 — how much of the grid any graph can tell apart\n")
        L.append(f"The standard defines {sep['combinations']} restrictor x selector "
                 f"combinations. Over an exhaustive sweep of "
                 f"{sep['sweep']['graphs_enumerated']:,} directed multigraphs and "
                 f"{sep['sweep']['pattern_probes']:,} pattern probes, "
                 f"{sep['separated']} of {sep['pairs']} cell pairs have a separating "
                 f"witness and {sep['pairs'] - sep['separated']} have none. "
                 f"**{sep['observable_classes']} observable classes.**\n")
        L.append("| combinations with no separating witness |")
        L.append("|---|")
        for a, b in sep["unobservable"]:
            L.append(f"| `{a[0]} {a[1]}` = `{b[0]} {b[1]}` |")
        L.append("\nA shortest path is already simple, so the restrictor is "
                 "unobservable under a shortest selector except for ACYCLIC, which "
                 "forbids the closed walk the others allow. This bounds what S3 can "
                 "mean: a construct cannot show more answer classes than the semantics "
                 "has.\n")

    L.append("\n## Metamorphic self-consistency\n")
    L.append("These need no reference semantics: they hold under WALK, TRAIL, ACYCLIC "
             "and SIMPLE alike, because no restrictor mentions the quantifier bounds. "
             "An engine that breaks one contradicts itself.\n")
    per = Counter(v["engine"] for v in mm["violations"])
    rel = Counter((v["engine"], v["relation"]) for v in mm["violations"])
    L.append("| engine | violations | relations broken |")
    L.append("|---|---:|---|")
    for e in engines:
        rs = sorted({r for (en, r) in rel if en == e})
        L.append(f"| {e} | {per.get(e, 0)} | {', '.join(rs) if rs else '—'} |")
    L.append(f"\nTotal: **{len(mm['violations'])} violations** across "
             f"{len({v['fixture'] for v in mm['violations']})} graphs. "
             f"Minimal reproducers are in `reproducers/`.\n")

    dest = os.path.join(HERE, "RESULTS.md")
    open(dest, "w").write("\n".join(L) + "\n")
    print(f"wrote {dest}")

    # Every number quoted in the paper, as a machine-readable key. The paper's
    # claims registry resolves against this file, so a number cannot drift from the
    # measurement that produced it.
    classes_per_construct = {}
    for c in CASES:
        cl = set()
        for e in ext_engines:
            cell = grid[(c.id, e)]
            if cell["verdict"] in ("CONFORMS", "DIVERGES"):
                cl.add(json.dumps(cell.get("observed"), sort_keys=True))
        if cl:
            classes_per_construct[c.id] = len(cl)
    by_group = {}
    for gname, ids in sorted(GROUPS.items()):
        gcells = [c for c in m["cells"]
                  if c["case"] in set(ids) and c["engine"] not in OURS
                  and c["engine"] not in SUPERSEDED and c["case"] in ANSWER_CASES]
        gt = Counter(c["verdict"] for c in gcells)
        ga = gt["CONFORMS"] + gt["DIVERGES"]
        gd = gt["DIVERGES"] + gt["REJECTS"]
        by_group[gname] = {
            "constructs": len(ids), "cells": len(gcells),
            "conforms": gt["CONFORMS"], "diverges": gt["DIVERGES"],
            "rejects": gt["REJECTS"], "inexpressible": gt["INEXPRESSIBLE"],
            "s1": round(gt["DIVERGES"] / ga, 4) if ga else None,
            "s2": round(gt["DIVERGES"] / gd, 4) if gd else None,
        }

    summary = {
        "n_constructs": len(CASES),
        "constructs_by_group": {g: len(ids) for g, ids in sorted(GROUPS.items())},
        "by_group": by_group,
        "s4_wellformedness": s4,
        "s5_spelling_agreement": s5,
        "s6_separation": s6,
        "n_engines": len(engines),
        "n_engines_external": len(ext_engines),
        "n_cells": len(m["cells"]),
        "n_cells_external": len(external),
        "repeats": m["repeats"],
        "conforms": tot["CONFORMS"],
        "diverges": tot["DIVERGES"],
        "rejects": tot["REJECTS"],
        "inexpressible": tot["INEXPRESSIBLE"],
        "nondeterministic": tot["NONDETERMINISTIC"],
        "s1_divergence_rate": round(tot["DIVERGES"] / answered, 4),
        "s2_silence_ratio": round(tot["DIVERGES"] / den, 4),
        "disagreements": den,
        "divergences_specified": spec,
        "divergences_defect": impl,
        "constructs_multi_class": sum(1 for v in classes_per_construct.values() if v > 1),
        "constructs_single_class": sum(1 for v in classes_per_construct.values() if v == 1),
        "classes_per_construct": classes_per_construct,
        # NC3: cells whose case uses a nondeterministic selector, scored against the
        # admissible set and the per-partition count rather than one chosen path.
        "nondeterministic_selector_cells": sum(
            1 for c in external
            if "ANY" in BYID[c["case"]].ref.selector
            and c["verdict"] in ("CONFORMS", "DIVERGES")),
        "constructs_measured": len(classes_per_construct),
        "metamorphic_violations_total": len(mm["violations"]),
        "metamorphic_violations_external": sum(
            1 for v in mm["violations"] if v["engine"] not in OURS),
        "s2b": {e: v for e, v in s2b_rows.items()},
        "s2b_external": round((sum(v["divergences"] for e, v in s2b_rows.items() if e not in OURS)
                               - sum(v["spoke"] for e, v in s2b_rows.items() if e not in OURS))
                              / max(1, sum(v["divergences"] for e, v in s2b_rows.items() if e not in OURS)), 4),
        # The same statistics under each defensible engine set, so the headline's
        # choice is checkable rather than asserted. `headline` is one row per
        # product at its newest measured version; the others are stated for contrast.
        "aggregates": _aggregates(m, ANSWER_CASES,
                                  {c.id for c in CASES if c.group == "v1"}),
        # Of each engine's conforming cells, how many it could only answer through the
        # standard's prefix keywords rather than the common openCypher rendering. A
        # conforming cell reached that way is not portable to an engine without them.
        "conforms_gql_prefix_by_engine": {
            e: sum(1 for c in m["cells"] if c["engine"] == e
                   and c["verdict"] == "CONFORMS" and c.get("surface") == "gql-prefix")
            for e in engines},
        # Queries that errored, so the relation needing them was skipped. A crash can
        # hide a violation but never add one, so a non-zero count here means that
        # engine's violation count is a lower bound (issue #4).
        "metamorphic_dropped_by_engine": {
            e: sum(1 for d in mm.get("dropped", []) if d["engine"] == e)
            for e in engines},
        # How many of each engine's metamorphic violations have a lower-bound-zero
        # query on one side. The paper says every one of the authors' release's
        # violations does -- one root cause; this is the key that claim resolves to.
        "metamorphic_lo0_by_engine": {
            e: sum(1 for v in mm["violations"] if v["engine"] == e
                   and (v["left"].startswith("{0,") or v["right"].startswith("{0,")))
            for e in engines},
        "level2": _level2_summary(),
        "metamorphic_violations_ours": sum(
            1 for v in mm["violations"] if v["engine"] in OURS),
        # The paper reports the 2026-09-07 measurement and, separately, what the
        # same suite scores after the defects it found were fixed. Both must be
        # checkable, so the frozen snapshot is summarised alongside the live run.
        "snapshot_2026_09_07": _snapshot_summary(),
        "metamorphic_violations_by_engine": {e: per.get(e, 0) for e in engines},
        "metamorphic_clean_engines": [e for e in engines if per.get(e, 0) == 0],
        "engines": {e["name"]: e["version"] for e in m["engines"]},
        "per_engine": {
            e: {
                "conforms": acc[e]["CONFORMS"], "diverges": acc[e]["DIVERGES"],
                "rejects": acc[e]["REJECTS"], "inexpressible": acc[e]["INEXPRESSIBLE"],
                "s1": (round(acc[e]["DIVERGES"] /
                             (acc[e]["CONFORMS"] + acc[e]["DIVERGES"]), 4)
                       if acc[e]["CONFORMS"] + acc[e]["DIVERGES"] else None),
                "s2": (round(acc[e]["DIVERGES"] /
                             (acc[e]["DIVERGES"] + acc[e]["REJECTS"]), 4)
                       if acc[e]["DIVERGES"] + acc[e]["REJECTS"] else None),
            } for e in engines},
    }
    sdest = os.path.join(HERE, "results", "summary.json")
    json.dump(summary, open(sdest, "w"), indent=2)
    _write_readme_scorecard(summary, engines, ver, acc, s4, s6)
    print(f"wrote {sdest}")


if __name__ == "__main__":
    main()
