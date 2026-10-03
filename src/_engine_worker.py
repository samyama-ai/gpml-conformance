"""A one-engine worker process, driven over stdin/stdout as newline-delimited JSON.

Why a separate process at all: pybind11 registers its exported types in a global
registry keyed by name, so two wheels built from the same C++ sources cannot both be
imported into one interpreter. `kuzu` and its fork `ladybug` both export `Database`, so
whichever imports second fails with "type Database is already registered", silently
falls back to a C API shared library the wheel does not ship, and reports a misleading
"could not find lbug C API shared library". Running the second engine in its own
interpreter is the only fix that does not involve dropping one of the two rows.

Protocol, one JSON object per line:
  {"op": "version"}                                  -> {"ok": true, "version": "..."}
  {"op": "load", "nodes": [...], "edges": [...],
   "primary": "N", "edge_label": "E"}                -> {"ok": true}
  {"op": "run", "q": "MATCH ..."}                    -> {"ok": true, "rows": [[s, t], ...]}
                                                     or {"ok": false, "error": "..."}
A refusal is `ok: false` with the engine's message. A crash closes the pipe, and the
adapter reports that as an engine error rather than as a silent empty answer.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import uuid


def main() -> int:
    module_name = sys.argv[1]
    workdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/gpml-cf"
    import importlib
    mod = importlib.import_module(module_name)
    con = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        op = msg.get("op")
        try:
            if op == "version":
                out = {"ok": True, "version": getattr(mod, "__version__", "unknown")}
            elif op == "load":
                path = os.path.join(workdir, f"{module_name}-{uuid.uuid4().hex}")
                shutil.rmtree(path, ignore_errors=True)
                os.makedirs(workdir, exist_ok=True)
                db = mod.Database(path)
                con = mod.Connection(db)
                primary, edge_label = msg["primary"], msg["edge_label"]
                propkeys = sorted({k for n in msg["nodes"] for k in n["props"]})
                secondary = sorted({l for n in msg["nodes"] for l in n["labels"]}
                                   - {primary})
                cols = ", ".join(f"{k} STRING" for k in propkeys)
                extra = "".join(f", is_{l} BOOLEAN" for l in secondary)
                con.execute(f"CREATE NODE TABLE {primary}(eid STRING, {cols}{extra}, "
                            f"PRIMARY KEY(eid))")
                con.execute(f"CREATE REL TABLE {edge_label}"
                            f"(FROM {primary} TO {primary}, eid STRING)")
                for n in msg["nodes"]:
                    vals = ", ".join(f"{k}: '{n['props'].get(k, '')}'" for k in propkeys)
                    ex = "".join(f", is_{l}: {str(l in n['labels']).lower()}"
                                 for l in secondary)
                    con.execute(f"CREATE (:{primary} {{eid: '{n['id']}', {vals}{ex}}})")
                for e in msg["edges"]:
                    con.execute(
                        f"MATCH (a:{primary}),(b:{primary}) "
                        f"WHERE a.eid='{e['src']}' AND b.eid='{e['dst']}' "
                        f"CREATE (a)-[:{edge_label} {{eid:'{e['id']}'}}]->(b)")
                out = {"ok": True}
            elif op == "run":
                r = con.execute(msg["q"])
                rows = []
                while r.has_next():
                    rows.append([str(x) for x in r.get_next()])
                out = {"ok": True, "rows": rows}
            else:
                out = {"ok": False, "error": f"unknown op {op!r}"}
        except Exception as ex:               # a refusal is a verdict, not a crash
            out = {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
