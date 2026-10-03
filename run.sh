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
docker rm -f cf-neo4j cf-neo4j-2026 cf-memgraph cf-age cf-arcade cf-falkor \
  cf-surreal cf-spanner >/dev/null 2>&1 || true
docker run -d --name cf-neo4j -p 7688:7687 \
  -e NEO4J_AUTH=neo4j/testpassword123 neo4j:5.26-community >/dev/null
# The 2026 line is a separate row in the map, not a replacement: it is where the
# GQL path-mode syntax arrived, so the two versions answer different cells.
# run_map.py has expected it on 7690 since it was added; run.sh did not start it,
# so `./run.sh` quietly produced a map with one engine missing.
docker run -d --name cf-neo4j-2026 -p 7690:7687 \
  -e NEO4J_AUTH=neo4j/testpassword123 neo4j:2026.04.0-community >/dev/null
docker run -d --name cf-memgraph -p 7689:7687 memgraph/memgraph:latest >/dev/null
docker run -d --name cf-age -p 5433:5432 -e POSTGRES_PASSWORD=postgres \
  apache/age:latest >/dev/null
# Every engine the map has a row for has to be started here. A row whose container
# run.sh does not start scores LOAD_FAILED across the board and the map ships with a
# hole in it -- which is how the neo4j-2026 column was empty for a week.
docker run -d --name cf-arcade -p 2480:2480 \
  -e JAVA_OPTS="-Darcadedb.server.rootPassword=playwithdata -Darcadedb.server.defaultDatabases=gpml[root]" \
  arcadedata/arcadedb:26.9.1 >/dev/null
docker run -d --name cf-falkor -p 6380:6379 falkordb/falkordb:latest >/dev/null
docker run -d --name cf-surreal -p 8010:8000 surrealdb/surrealdb:latest \
  start --user root --pass root >/dev/null
docker run -d --name cf-spanner -p 9010:9010 -p 9020:9020 \
  gcr.io/cloud-spanner-emulator/emulator:1.5.58 >/dev/null

echo "== waiting for engines"
for _ in $(seq 1 90); do
  if "$PYBIN" - <<'PROBE' >/dev/null 2>&1
import sys
sys.path.insert(0, "src")
# Opening a connection is not readiness. Neo4j accepts Bolt before the database is
# writable, so a connect-only probe returns success and the first cases of the run then
# score LOAD_FAILED. Each engine must complete a write and a read. Every engine with a
# row is probed here: one left out is a column of LOAD_FAILED that nobody notices until
# the map is published.
import fixtures
from engines_adapters import (AgeAdapter, ArcadeAdapter, BoltAdapter, FalkorAdapter,
                              SpannerAdapter, SurrealAdapter)
g = fixtures.FIXTURES["single"]()
L, E = fixtures.PRIMARY_LABEL["single"], fixtures.EDGE_LABEL["single"]
for a in (BoltAdapter("neo4j", "bolt://localhost:7688", ("neo4j", "testpassword123")),
          BoltAdapter("neo4j-2026", "bolt://localhost:7690", ("neo4j", "testpassword123")),
          BoltAdapter("memgraph", "bolt://localhost:7689", None),
          AgeAdapter("host=localhost port=5433 dbname=postgres "
                     "user=postgres password=postgres"),
          ArcadeAdapter(), FalkorAdapter(), SurrealAdapter(), SpannerAdapter()):
    a.load(g, L, E)
PROBE
  then echo "   all engines ready"; break; fi
  sleep 2
done

echo "== Gate B: the reference must reproduce the standard's published answers"
"$VENV/bin/pytest" tests/ -q

echo "== conformance map"
"$PYBIN" src/run_map.py

echo "== level 2: edge-sequence refinement"
"$PYBIN" src/run_level2.py

echo "== metamorphic self-consistency"
"$PYBIN" src/run_metamorphic.py

echo "== summary"
"$PYBIN" src/summarise.py
"$PYBIN" src/report.py

echo
echo "RESULTS.md regenerated."
