"""Regenerate every figure in the paper from results/*.json. No hand-drawn numbers.

Palette: a four-state status set, validated for colour-vision deficiency and for
contrast against a white surface (dataviz validator, light mode, all checks pass for
the three informative hues; the fourth slot is a deliberate neutral for "absent").
Every cell also carries a glyph, so identity is never colour alone and the figures
survive greyscale printing.
"""
import json, os, sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
from suite import CASES

CONFORMS, DIVERGES, REJECTS, ABSENT = "#1B7F5F", "#B42318", "#1D4ED8", "#C7CBD1"
COLOR = {"CONFORMS": CONFORMS, "DIVERGES": DIVERGES, "REJECTS": REJECTS,
         "INEXPRESSIBLE": ABSENT, "NONDETERMINISTIC": "#6B21A8"}
GLYPH = {"CONFORMS": "✓", "DIVERGES": "✗", "REJECTS": "!", "INEXPRESSIBLE": "–",
         "NONDETERMINISTIC": "?"}
INK, MUTED = "#1F2933", "#667085"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": "#D9DDE3", "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "figure.facecolor": "white", "axes.facecolor": "white",
})


def load():
    m = json.load(open(os.path.join(HERE, "results", "map.json")))
    mm = json.load(open(os.path.join(HERE, "results", "metamorphic.json")))
    return m, mm


def fig_map(m, path):
    engines = [e["name"] for e in m["engines"]]
    grid = {(c["case"], c["engine"]): c["verdict"] for c in m["cells"]}
    ncase, neng = len(CASES), len(engines)
    fig, ax = plt.subplots(figsize=(1.15 * neng + 3.6, 0.34 * ncase + 1.5))
    for i, c in enumerate(CASES):
        y = ncase - 1 - i
        for j, e in enumerate(engines):
            v = grid[(c.id, e)]
            # a 2px surface gap between fills: inset each cell
            ax.add_patch(plt.Rectangle((j + 0.03, y + 0.06), 0.94, 0.88,
                                       facecolor=COLOR[v], edgecolor="none"))
            ax.text(j + 0.5, y + 0.5, GLYPH[v], ha="center", va="center",
                    color="white" if v != "INEXPRESSIBLE" else "#4A5260",
                    fontsize=10, fontweight="bold")
    ax.set_xlim(0, neng)
    ax.set_ylim(0, ncase)
    ax.set_xticks([j + 0.5 for j in range(neng)])
    ax.set_xticklabels(engines, rotation=0, fontsize=8.5)
    ax.xaxis.set_ticks_position("top")
    ax.set_yticks([ncase - 0.5 - i for i in range(ncase)])
    ax.set_yticklabels([c.id for c in CASES], fontsize=8)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.legend(handles=[Patch(facecolor=COLOR[k], label=f"{GLYPH[k]}  {k.lower()}")
                       for k in ("CONFORMS", "DIVERGES", "REJECTS", "INEXPRESSIBLE")],
              loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=4,
              frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_attribution(m, path):
    """Divergences split into documented language differences and real defects."""
    engines = [e["name"] for e in m["engines"]]
    spec = Counter()
    defect = Counter()
    for c in m["cells"]:
        if c["verdict"] != "DIVERGES":
            continue
        if c.get("verdict_vs_declared") == "CONFORMS":
            spec[c["engine"]] += 1
        else:
            defect[c["engine"]] += 1
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    ys = range(len(engines))
    a = [spec[e] for e in engines]
    b = [defect[e] for e in engines]
    ax.barh(list(ys), a, color="#94A3B8", height=0.52, label="documented language difference")
    ax.barh(list(ys), b, left=[x + 0.06 for x in a], color=DIVERGES, height=0.52,
            label="departs from the standard it implements")
    for i, e in enumerate(engines):
        tot = spec[e] + defect[e]
        if tot:
            ax.text(tot + 0.15, i, str(tot), va="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(engines, fontsize=8.5)
    ax.set_xlabel("divergences from the ISO reference semantics")
    ax.set_xlim(0, max(1, max(spec[e] + defect[e] for e in engines)) + 0.8)
    ax.grid(axis="x", color="#EEF1F4", lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center",
              bbox_to_anchor=(0.5, -0.30), ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_metamorphic(mm, m, path):
    engines = [e["name"] for e in m["engines"]]
    rels = sorted({v["relation"] for v in mm["violations"]})
    counts = {r: [sum(1 for v in mm["violations"]
                      if v["engine"] == e and v["relation"] == r) for e in engines]
              for r in rels}
    fig, ax = plt.subplots(figsize=(6.4, 2.7))
    left = [0.0] * len(engines)
    shades = ["#1D4ED8", "#60A5FA", "#A5C6FF"]
    for k, r in enumerate(rels):
        ax.barh(range(len(engines)), counts[r], left=[x + (0.06 if x else 0) for x in left],
                color=shades[k % len(shades)], height=0.52, label=r)
        left = [a + b for a, b in zip(left, counts[r])]
    for i, e in enumerate(engines):
        ax.text(left[i] + 0.5, i, str(int(left[i])) if left[i] else "0",
                va="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(range(len(engines)))
    ax.set_yticklabels(engines, fontsize=8.5)
    ax.set_xlabel("metamorphic violations (no reference semantics involved)")
    ax.set_xlim(0, max(left) + 3)
    ax.grid(axis="x", color="#EEF1F4", lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center",
              bbox_to_anchor=(0.5, -0.30), ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    m, mm = load()
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figures")
    os.makedirs(outdir, exist_ok=True)
    fig_map(m, os.path.join(outdir, "fig1_map.png"))
    fig_attribution(m, os.path.join(outdir, "fig2_attribution.png"))
    fig_metamorphic(mm, m, os.path.join(outdir, "fig3_metamorphic.png"))
    print("wrote", outdir)
