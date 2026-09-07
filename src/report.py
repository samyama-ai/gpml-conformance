import json, os, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
from suite import CASES

SYM = {"CONFORMS": "=", "DIVERGES": "X", "REJECTS": "!", "INEXPRESSIBLE": "-",
       "NONDETERMINISTIC": "?", "LOAD_FAILED": "L"}


def main():
    m = json.load(open(os.path.join(HERE, "results", "map.json")))
    engines = [e["name"] for e in m["engines"]]
    grid = {(c["case"], c["engine"]): c for c in m["cells"]}

    w = max(len(c.id) for c in CASES)
    print(" " * (w + 2) + "  ".join(f"{e[:9]:>9s}" for e in engines))
    for c in CASES:
        row = "  ".join(f"{SYM[grid[(c.id, e)]['verdict']]:>9s}" for e in engines)
        print(f"{c.id:<{w}s}  {row}")
    print("\n= conforms   X diverges   ! rejects   - inexpressible   ? nondeterministic\n")

    acc = {e: Counter() for e in engines}
    for c in m["cells"]:
        acc[c["engine"]][c["verdict"]] += 1
    print(f"{'engine':<12s} {'conf':>5s} {'div':>5s} {'rej':>5s} {'inex':>5s}  S1_div_rate  S2_silence")
    for e in engines:
        a = acc[e]
        answered = a["CONFORMS"] + a["DIVERGES"]
        s1 = a["DIVERGES"] / answered if answered else float("nan")
        denom = a["DIVERGES"] + a["REJECTS"]
        s2 = a["DIVERGES"] / denom if denom else float("nan")
        print(f"{e:<12s} {a['CONFORMS']:5d} {a['DIVERGES']:5d} {a['REJECTS']:5d} "
              f"{a['INEXPRESSIBLE']:5d}  {s1:11.3f}  {s2:10.3f}")

    tot = Counter(c["verdict"] for c in m["cells"])
    answered = tot["CONFORMS"] + tot["DIVERGES"]
    print(f"\nS1 overall divergence rate  {tot['DIVERGES']}/{answered} = "
          f"{tot['DIVERGES']/answered:.3f}")
    print(f"S2 overall silence ratio    {tot['DIVERGES']}/"
          f"{tot['DIVERGES']+tot['REJECTS']} = "
          f"{tot['DIVERGES']/(tot['DIVERGES']+tot['REJECTS']):.3f}")

    print("\nS3 distinct answer classes per construct (over engines that answered):")
    for c in CASES:
        classes = defaultdict(list)
        for e in engines:
            cell = grid[(c.id, e)]
            if cell["verdict"] in ("CONFORMS", "DIVERGES"):
                key = json.dumps(cell.get("observed"), sort_keys=True)
                classes[key].append(e)
        if classes:
            print(f"  {c.id:<32s} {len(classes)} class(es)  " +
                  " | ".join(",".join(v) for v in classes.values()))


if __name__ == "__main__":
    main()
