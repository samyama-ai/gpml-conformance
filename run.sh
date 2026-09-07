#!/usr/bin/env bash
# One command: bring the engines up, gate the oracle, run the suite, write RESULTS.md.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-python3}
VENV=${VENV:-.venv}

if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt
fi
PYBIN="$VENV/bin/python"

echo "== starting engines"
docker rm -f cf-neo4j cf-memgraph cf-age >/dev/null 2>&1 || true
docker run -d --name cf-neo4j -p 7688:7687 \
  -e NEO4J_AUTH=neo4j/testpassword123 neo4j:5.26-community >/dev/null
docker run -d --name cf-memgraph -p 7689:7687 memgraph/memgraph:latest >/dev/null
docker run -d --name cf-age -p 5433:5432 -e POSTGRES_PASSWORD=postgres \
  apache/age:latest >/dev/null

echo "== waiting for engines"
for _ in $(seq 1 60); do
  if "$PYBIN" - <<'PROBE' >/dev/null 2>&1
import sys
sys.path.insert(0, "src")
from engines_adapters import BoltAdapter, AgeAdapter
BoltAdapter("neo4j", "bolt://localhost:7688", ("neo4j", "testpassword123"))
BoltAdapter("memgraph", "bolt://localhost:7689", None)
AgeAdapter("host=localhost port=5433 dbname=postgres user=postgres password=postgres")
PROBE
  then break; fi
  sleep 2
done

echo "== Gate B: the reference must reproduce the standard's published answers"
"$VENV/bin/pytest" tests/ -q

echo "== conformance map"
"$PYBIN" src/run_map.py

echo "== metamorphic self-consistency"
"$PYBIN" src/run_metamorphic.py

echo "== summary"
"$PYBIN" src/summarise.py
"$PYBIN" src/report.py

echo
echo "RESULTS.md regenerated."
