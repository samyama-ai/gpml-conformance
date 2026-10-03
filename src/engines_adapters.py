"""Engine adapters. Each one loads a fixture and runs a dialect query, returning the
multiset of (s, t) pairs -- comparison level L1 -- or an EngineError.

An adapter must not interpret the query or repair it. If the engine refuses, that is
data (verdict REJECTS), not a bug in the harness.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from graph import PropertyGraph


class EngineError(Exception):
    """The engine refused the query. A verdict, not a failure."""


class EngineUnavailable(Exception):
    """The engine could not be reached, or died mid-query.

    Deliberately NOT a subclass of EngineError. A refusal is a conforming act for an
    ill-formed pattern and a visible disagreement for a well-formed one, so an engine
    that crashed must never be scored as one -- a container that runs out of memory
    would otherwise be recorded as an engine that correctly refused, and the map would
    publish a dead process as a result.
    """


@dataclass
class Answer:
    pairs: Counter                       # multiset of (s, t)
    raw_rows: int
    # Diagnostics the engine attached to the result: warnings, notices,
    # notifications. `None` means this adapter cannot ask -- which is a different
    # fact from an empty list, and the map records the difference.
    diagnostics: Optional[list] = None


def _counter(rows, diagnostics=None) -> Answer:
    c = Counter()
    for r in rows:
        c[(str(r[0]), str(r[1]))] += 1
    return Answer(c, len(rows), diagnostics)


# --------------------------------------------------------------------------


class KuzuAdapter:
    """Kuzu, and its live fork.

    Kuzu itself is frozen: 0.11.3 is the final release, the repository was archived
    on 2025-10-10 and Kuzu Inc. was acquired. Its row can never change again, which
    is worth saying in a conformance table -- a divergence here is permanent, not a
    bug someone might fix. LadybugDB continues the same codebase under the same
    embedded Python API, so the same adapter drives both and the lineage stays in
    the matrix with a version that can still move.
    """

    name = "kuzu"
    dialect = "cypher"
    version = None

    def __init__(self, workdir: str, module: str = "kuzu", name: str | None = None):
        import importlib
        self._kuzu = importlib.import_module(module)
        self.workdir = workdir
        if name:
            self.name = name
        self.version = getattr(self._kuzu, "__version__", "unknown")

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        import shutil, os, uuid
        path = os.path.join(self.workdir, f"{self.name}-{uuid.uuid4().hex}")
        shutil.rmtree(path, ignore_errors=True)
        self.db = self._kuzu.Database(path)
        self.con = self._kuzu.Connection(self.db)
        propkeys = sorted({k for n in g.nodes.values() for k, _ in n.props})
        secondary = sorted({l for n in g.nodes.values() for l in n.labels} - {primary})
        cols = ", ".join(f"{k} STRING" for k in propkeys)
        # Kuzu nodes carry exactly one label (the table). Secondary labels are kept
        # as boolean columns so no information is lost, but a multi-label node
        # pattern has no Kuzu syntax -- such cases score INEXPRESSIBLE.
        extra = "".join(f", is_{l} BOOLEAN" for l in secondary)
        self.con.execute(
            f"CREATE NODE TABLE {primary}(eid STRING, {cols}{extra}, PRIMARY KEY(eid))")
        self.con.execute(
            f"CREATE REL TABLE {edge_label}(FROM {primary} TO {primary}, eid STRING)")
        for n in g.nodes.values():
            vals = ", ".join(f"{k}: '{dict(n.props).get(k, '')}'" for k in propkeys)
            ex = "".join(f", is_{l}: {str(l in n.labels).lower()}" for l in secondary)
            self.con.execute(f"CREATE (:{primary} {{eid: '{n.id}', {vals}{ex}}})")
        for e in g.edges.values():
            self.con.execute(
                f"MATCH (a:{primary}),(b:{primary}) WHERE a.eid='{e.src}' AND b.eid='{e.dst}' "
                f"CREATE (a)-[:{edge_label} {{eid:'{e.id}'}}]->(b)")

    def run(self, q: str) -> Answer:
        try:
            r = self.con.execute(q)
        except Exception as ex:
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        rows = []
        while r.has_next():
            rows.append(r.get_next())
        # Neither Kuzu 0.11 nor LadybugDB exposes a warning or notification channel.
        return _counter(rows, None)


class DuckPGQAdapter:
    name = "duckpgq"
    dialect = "pgq"
    version = None

    def __init__(self, workdir: str):
        import duckdb
        self._duckdb = duckdb
        self.version = duckdb.__version__

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        con = self._duckdb.connect()
        con.execute("INSTALL duckpgq FROM community; LOAD duckpgq;")
        propkeys = sorted({k for n in g.nodes.values() for k, _ in n.props})
        secondary = sorted({l for n in g.nodes.values() for l in n.labels} - {primary})
        cols = ", ".join(f"{k} VARCHAR" for k in propkeys)
        extra = "".join(f", is_{l} BOOLEAN" for l in secondary)
        con.execute(f"CREATE TABLE {primary}(eid VARCHAR PRIMARY KEY, {cols}{extra})")
        for n in g.nodes.values():
            vals = ", ".join("'" + str(dict(n.props).get(k, "")) + "'" for k in propkeys)
            ex = "".join(", " + str(l in n.labels).upper() for l in secondary)
            con.execute(f"INSERT INTO {primary} VALUES ('{n.id}', {vals}{ex})")
        con.execute(
            f"CREATE TABLE {edge_label}(eid VARCHAR, src VARCHAR, dst VARCHAR)")
        for e in g.edges.values():
            con.execute(f"INSERT INTO {edge_label} VALUES ('{e.id}','{e.src}','{e.dst}')")
        con.execute(f"""CREATE PROPERTY GRAPH g
            VERTEX TABLES ({primary})
            EDGE TABLES ({edge_label} SOURCE KEY (src) REFERENCES {primary} (eid)
                         DESTINATION KEY (dst) REFERENCES {primary} (eid));""")
        self.con = con

    def run(self, q: str) -> Answer:
        try:
            rows = self.con.execute(q).fetchall()
        except Exception as ex:
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        # DuckDB's Python API exposes no per-statement warning channel.
        return _counter(rows, None)


class BoltAdapter:
    """Neo4j and Memgraph both speak Bolt and openCypher."""
    dialect = "cypher"

    def __init__(self, name: str, uri: str, auth):
        from neo4j import GraphDatabase
        self.name = name
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self.version = self._server_version()

    def _server_version(self):
        try:
            with self.driver.session() as s:
                for comp in s.run("CALL dbms.components() YIELD name, versions "
                                  "RETURN name, versions"):
                    return f"{comp['name']} {comp['versions'][0]}"
        except Exception:
            return "unknown"

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
            for n in g.nodes.values():
                labels = "".join(f":{l}" for l in sorted(n.labels))
                props = ", ".join(f"{k}: '{v}'" for k, v in n.props)
                sep = ", " if props else ""
                s.run(f"CREATE (x{labels} {{eid: '{n.id}'{sep}{props}}})")
            for e in g.edges.values():
                lbl = sorted(e.labels)[0] if e.labels else "REL"
                s.run(f"MATCH (a),(b) WHERE a.eid='{e.src}' AND b.eid='{e.dst}' "
                      f"CREATE (a)-[:{lbl} {{eid:'{e.id}'}}]->(b)")

    def run(self, q: str) -> Answer:
        try:
            with self.driver.session() as s:
                res = s.run(q)
                rows = [tuple(r.values()) for r in res]
                diags = []
                try:
                    summary = res.consume()
                    for n in (summary.notifications or []):
                        diags.append({
                            "code": n.get("code", ""),
                            "title": n.get("title", ""),
                            "description": n.get("description", ""),
                            "severity": n.get("severity", ""),
                        })
                except Exception:
                    diags = None          # driver or server too old to ask
        except Exception as ex:
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        return _counter(rows, diags)


class AgeAdapter:
    name = "apache-age"
    dialect = "cypher"

    def __init__(self, dsn: str):
        import psycopg2
        self.psycopg2 = psycopg2
        self.dsn = dsn
        self.conn = None
        self.version = self._version()

    def _version(self):
        import psycopg2
        with psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='age'")
            r = cur.fetchone()
            return f"age {r[0]}" if r else "age unknown"

    def _conn(self):
        c = self.psycopg2.connect(self.dsn)
        c.autocommit = True
        cur = c.cursor()
        cur.execute("LOAD 'age'; SET search_path = ag_catalog, \"$user\", public;")
        return c, cur

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        if getattr(self, "conn", None) is None:
            self.conn, self.cur = self._conn()
        c, cur = self.conn, self.cur
        # AGE 1.8 resolves create_graph/drop_graph on the `name` type; an unknown
        # string literal fails with "graph name is invalid", so cast explicitly.
        cur.execute("SELECT count(*) FROM ag_graph WHERE name='cfgraph'")
        if cur.fetchone()[0]:
            cur.execute("SELECT drop_graph('cfgraph'::name, true)")
        cur.execute("SELECT create_graph('cfgraph'::name)")
        for n in g.nodes.values():
            labels = [primary] + sorted(set(n.labels) - {primary})
            lbl = labels[0]
            props = ", ".join(f"{k}: '{v}'" for k, v in n.props)
            sep = ", " if props else ""
            extra = "".join(f", is_{l}: true" for l in labels[1:])
            cur.execute(
                f"SELECT * FROM cypher('cfgraph', $$ CREATE (:{lbl} "
                f"{{eid: '{n.id}'{sep}{props}{extra}}}) $$) AS (v agtype)")
        for e in g.edges.values():
            lbl = sorted(e.labels)[0] if e.labels else "REL"
            cur.execute(
                f"SELECT * FROM cypher('cfgraph', $$ MATCH (a),(b) "
                f"WHERE a.eid='{e.src}' AND b.eid='{e.dst}' "
                f"CREATE (a)-[:{lbl} {{eid:'{e.id}'}}]->(b) $$) AS (v agtype)")

    def run(self, q: str) -> Answer:
        # AGE wraps Cypher in a SQL function and needs an explicit column list.
        wrapped = (f"SELECT * FROM cypher('cfgraph', $$ {q} $$) AS (s agtype, t agtype)")
        try:
            del self.conn.notices[:]      # notices accumulate on the connection
            self.cur.execute(wrapped)
            rows = self.cur.fetchall()
            diags = [{"code": "", "title": "", "description": n.strip(),
                      "severity": "NOTICE"} for n in self.conn.notices]
        except Exception as ex:
            try:
                self.conn.rollback()
            except Exception:
                pass
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        return _counter([(str(a).strip('"'), str(b).strip('"')) for a, b in rows], diags)


class SamyamaAdapter:
    """Samyama-Graph, over its HTTP query endpoint.

    This is the authors' own engine. It is measured by the same suite as every other
    row and excluded from the paper's headline statistics; see the conflict-of-interest
    note in README.md.

    It owns its server process and restarts it with --ephemeral for every fixture,
    rather than resetting a shared instance with `MATCH (n) DETACH DELETE n`. During
    development a long-lived shared instance was found holding hundreds of edges with
    dangling endpoints, which silently contaminated every measurement taken against it.
    We could not reduce that to a reproducible defect -- DETACH DELETE resets correctly
    in isolation across all six fixtures -- so no bug is claimed. A fresh process is
    simply the only reset whose semantics are unambiguous, and the measurement should
    not rest on one we could not explain.
    """
    name = "samyama-graph"
    dialect = "cypher"

    def __init__(self, binary: str | None = None, port: int = 8099,
                 resp_port: int = 6399, name: str | None = None,
                 build: str | None = None):
        import os
        import urllib.request
        self._urllib = urllib.request
        self.binary = binary or os.environ.get(
            "SAMYAMA_BIN",
            os.path.expanduser("~/projects/graph_ws/samyama-graph/target/release/samyama"))
        if not os.path.exists(self.binary):
            raise FileNotFoundError(self.binary)
        if name:
            self.name = name
        # Which build this is. The binary reports the same version string for the
        # release tag and for the development head, so the git description is the
        # only thing that tells them apart -- and the paper's table reports the
        # release, like every other row.
        self.build = build or "unspecified"
        self.port, self.resp_port = port, resp_port
        self.base_url = f"http://localhost:{port}"
        self.proc = None
        self._start()
        self.version = self._version()

    # -- process ------------------------------------------------------------
    def _port_is_free(self) -> bool:
        import socket
        with socket.socket() as sk:
            sk.settimeout(0.5)
            return sk.connect_ex(("127.0.0.1", self.port)) != 0

    def _start(self):
        import subprocess, time
        self._stop()
        # Wait for the port to actually be released. Without this the new process
        # loses the bind race and dies, the readiness probe below then succeeds
        # against the *old* server, and every fixture loads into one accumulating
        # store -- which is exactly the "restart" that silently did nothing.
        for _ in range(80):
            if self._port_is_free():
                break
            time.sleep(0.25)
        else:
            raise EngineError(f"port {self.port} never freed; a stale samyama is "
                              f"holding it")
        self.proc = subprocess.Popen(
            [self.binary, "--port", str(self.resp_port),
             "--http-port", str(self.port), "--ephemeral"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        for _ in range(120):
            time.sleep(0.25)
            try:
                self._post("RETURN 1")
                break
            except Exception:
                continue
        else:
            raise EngineError("samyama did not become ready")
        # A fresh --ephemeral store is empty. If it is not, we are talking to a
        # server we did not start, and nothing measured against it means anything.
        for q, what in (("MATCH (n) RETURN n", "node"), ("MATCH ()-[r]->() RETURN r", "edge")):
            n = len(self._post(q).get("records") or [])
            if n:
                raise EngineError(f"a freshly started --ephemeral store already holds "
                                  f"{n} {what}(s); this is not the process we started")

    def _stop(self):
        import time
        if getattr(self, "proc", None) is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()
            self.proc = None
            time.sleep(0.3)

    def __del__(self):
        try:
            self._stop()
        except Exception:
            pass

    # -- protocol -----------------------------------------------------------
    def _post(self, query: str):
        import json as _json
        req = self._urllib.Request(
            f"{self.base_url}/api/query",
            data=_json.dumps({"query": query}).encode(),
            headers={"Content-Type": "application/json"})
        with self._urllib.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode())

    def _version(self):
        """Report the build label, and flag it if the binary disagrees.

        The build label comes from the git tag and is authoritative; the engine's own
        `engine_version` field is the cross-check. When the two agree the row carries
        one version, which is all a reader needs. When they disagree the row says so,
        because a table that silently prints the label it was told would hide exactly
        the case where the wrong binary was measured.
        """
        try:
            v = self._post("RETURN 1").get("engine_version")
        except Exception:
            v = None
        label = self.build.lstrip("v")
        if v and str(v).lstrip("v") != label:
            return f"samyama {self.build} (binary reports {v})"
        return f"samyama {self.build}"

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        self._start()          # a fresh --ephemeral process is the only trusted reset
        for n in g.nodes.values():
            labels = "".join(f":{l}" for l in sorted(n.labels))
            props = ", ".join(f'{k}: "{v}"' for k, v in n.props)
            sep = ", " if props else ""
            self._post(f'CREATE (x{labels} {{eid: "{n.id}"{sep}{props}}})')
        for e in g.edges.values():
            lbl = sorted(e.labels)[0] if e.labels else "REL"
            self._post(f'MATCH (a),(b) WHERE a.eid="{e.src}" AND b.eid="{e.dst}" '
                       f'CREATE (a)-[:{lbl} {{eid:"{e.id}"}}]->(b)')
        got = len(self._post(
            'MATCH (x)-[r]->(y) RETURN x.eid, y.eid').get("records") or [])
        if got != len(g.edges):
            raise EngineError(
                f"load verification failed: {got} edges present, {len(g.edges)} expected")

    def run(self, q: str) -> Answer:
        # Samyama's Cypher wants double-quoted string literals.
        q = q.replace("'", '"')
        try:
            res = self._post(q)
        except Exception as ex:
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        if isinstance(res, dict) and res.get("error"):
            raise EngineError(str(res["error"])[:300])
        diags = [{"code": n.get("code", ""), "title": n.get("title", ""),
                  "description": n.get("description", ""),
                  "severity": n.get("severity", "")}
                 for n in (res.get("notifications") or [])]
        return _counter(res.get("records") or [], diags)


class ArcadeAdapter:
    """ArcadeDB, over its HTTP command API.

    ArcadeDB ships GQL path modes -- WALK, TRAIL and ACYCLIC -- with TRAIL as the
    default, which is a documented departure from the standard's WALK. It has no
    SIMPLE and no selector keywords. It is in the matrix because it is the second
    engine whose default path mode is not the standard's, and because its GQL surface
    is moving fast enough to be worth a gate.

    Bolt would have cost no adapter at all, but the shipped image starts no Bolt
    plugin, and configuring one is a deployment choice we would then be measuring
    instead of the engine.
    """

    name = "arcadedb"
    dialect = "cypher"

    def __init__(self, base="http://localhost:2480", db="gpml",
                 auth=("root", "playwithdata")):
        import requests
        self._requests = requests
        self.base, self.db, self.auth = base.rstrip("/"), db, auth
        self.version = self._version()


    def _http(self, fn, *a, **kw):
        """Run an HTTP call, telling a refusal apart from a dead engine.

        A 4xx or 5xx with a body is the engine answering: it parsed the request and
        said no. A transport failure -- connection reset, closed socket, timeout -- is
        the engine not being there, which is not a verdict about the query.
        """
        try:
            return fn(*a, **kw)
        except Exception as ex:
            if type(ex).__name__ in ("ConnectionError", "ReadTimeout", "Timeout",
                                     "ChunkedEncodingError", "ConnectTimeout"):
                raise EngineUnavailable(f"{self.name}: {type(ex).__name__}: "
                                        f"{str(ex)[:160]}") from ex
            raise

    def _post(self, path, payload):
        r = self._http(self._requests.post, f"{self.base}{path}", json=payload,
                       auth=self.auth, timeout=60)
        if r.status_code >= 400:
            raise EngineError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def _command(self, command, language="opencypher"):
        return self._post(f"/api/v1/command/{self.db}",
                          {"language": language, "command": command})

    def _version(self):
        try:
            return self._post("/api/v1/server", {}).get("version", "unknown")
        except Exception:
            try:
                return str(self._requests.get(f"{self.base}/api/v1/server",
                                              auth=self.auth, timeout=20).json()
                           .get("version", "unknown"))
            except Exception:
                return "unknown"

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        # ArcadeDB is schema-full: a type has to exist before a row can carry it.
        for stmt in (f"DELETE FROM `{edge_label}` UNSAFE", f"DELETE FROM `{primary}` UNSAFE"):
            try:
                self._command(stmt, language="sql")
            except EngineError:
                pass                      # first run: the type does not exist yet
        extra = sorted({lbl for n in g.nodes.values() for lbl in n.labels} - {primary})
        for t in [primary] + extra:
            try:
                self._command(f"CREATE VERTEX TYPE `{t}` IF NOT EXISTS", language="sql")
            except EngineError:
                pass
        try:
            self._command(f"CREATE EDGE TYPE `{edge_label}` IF NOT EXISTS", language="sql")
        except EngineError:
            pass
        for n in g.nodes.values():
            labels = "".join(f":`{l}`" for l in sorted(n.labels))
            props = ", ".join(f"{k}: '{v}'" for k, v in n.props)
            sep = ", " if props else ""
            self._command(f"CREATE (x{labels} {{eid: '{n.id}'{sep}{props}}})")
        for e in g.edges.values():
            lbl = sorted(e.labels)[0] if e.labels else "REL"
            self._command(f"MATCH (a),(b) WHERE a.eid='{e.src}' AND b.eid='{e.dst}' "
                          f"CREATE (a)-[:`{lbl}` {{eid:'{e.id}'}}]->(b)")

    def run(self, q: str) -> Answer:
        res = self._command(q)
        rows = []
        for r in res.get("result", []):
            vals = [r.get("s"), r.get("t")]
            rows.append(tuple(vals))
        return _counter(rows, None)


class FalkorAdapter:
    """FalkorDB, over its own client.

    openCypher only -- no path modes, no selectors. It is in the matrix for one
    reason: its uniqueness semantics for `*m..n` are undocumented, so measuring it
    produces a fact rather than a restatement of a manual. Every other engine in the
    matrix has a documented mode to be held to; this one has none, so its row carries
    no declared-mode column.
    """

    name = "falkordb"
    dialect = "cypher"

    def __init__(self, host="localhost", port=6380):
        from falkordb import FalkorDB
        self._db = FalkorDB(host=host, port=port)
        self._graph = None
        self.version = self._version()

    def _version(self):
        try:
            info = self._db.connection.execute_command("INFO", "server")
            if isinstance(info, dict):
                return f"falkordb {info.get('redis_version', 'unknown')}"
            return "falkordb unknown"
        except Exception:
            return "unknown"

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        self._graph = self._db.select_graph("gpml")
        try:
            self._graph.delete()
        except Exception:
            pass                          # nothing to drop on the first fixture
        self._graph = self._db.select_graph("gpml")
        for n in g.nodes.values():
            labels = "".join(f":{l}" for l in sorted(n.labels))
            props = ", ".join(f"{k}: '{v}'" for k, v in n.props)
            sep = ", " if props else ""
            self._graph.query(f"CREATE (x{labels} {{eid: '{n.id}'{sep}{props}}})")
        for e in g.edges.values():
            lbl = sorted(e.labels)[0] if e.labels else "REL"
            self._graph.query(
                f"MATCH (a),(b) WHERE a.eid='{e.src}' AND b.eid='{e.dst}' "
                f"CREATE (a)-[:{lbl} {{eid:'{e.id}'}}]->(b)")

    def run(self, q: str) -> Answer:
        try:
            res = self._graph.query(q)
        except Exception as ex:
            if "Connection" in type(ex).__name__ or "closed" in str(ex).lower():
                raise EngineUnavailable(f"{self.name}: {ex}") from ex
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        return _counter([tuple(r) for r in res.result_set], None)


class SurrealAdapter:
    """SurrealDB, over its ISO GQL endpoint.

    The widest GQL path-pattern surface of any engine that runs locally for free:
    all four path modes, ALL / ANY / ALL SHORTEST / ANY SHORTEST and the counted
    forms, and the full quantifier set. Its own documentation states a deviation
    before anyone measures it -- the match mode is fixed to distinct edges, so WALK
    and TRAIL both reduce to edge-unique traversal -- which makes it the one row in
    the matrix where a declared divergence can be checked against the declaration.

    Data goes in through SurrealQL, which is the only way to put it there; the
    measurement itself is always sent to /gql.
    """

    name = "surrealdb"
    dialect = "gql"                      # takes the standard's own spelling, not openCypher's

    def __init__(self, base="http://localhost:8010", ns="gpml", db="gpml",
                 auth=("root", "root")):
        import requests
        self._requests = requests
        self.base, self.ns, self.db, self.auth = base.rstrip("/"), ns, db, auth
        self._headers = {"Accept": "application/json",
                         "surreal-ns": ns, "surreal-db": db}
        self._sql(f"DEFINE NAMESPACE IF NOT EXISTS {ns};")
        self._sql(f"DEFINE DATABASE IF NOT EXISTS {db};")
        self.version = self._version()

    def _version(self):
        try:
            return self._requests.get(f"{self.base}/version", timeout=20).text.strip()
        except Exception:
            return "unknown"


    def _http(self, fn, *a, **kw):
        """Run an HTTP call, telling a refusal apart from a dead engine.

        A 4xx or 5xx with a body is the engine answering: it parsed the request and
        said no. A transport failure -- connection reset, closed socket, timeout -- is
        the engine not being there, which is not a verdict about the query.
        """
        try:
            return fn(*a, **kw)
        except Exception as ex:
            if type(ex).__name__ in ("ConnectionError", "ReadTimeout", "Timeout",
                                     "ChunkedEncodingError", "ConnectTimeout"):
                raise EngineUnavailable(f"{self.name}: {type(ex).__name__}: "
                                        f"{str(ex)[:160]}") from ex
            raise

    def _post(self, path, body, content_type):
        h = dict(self._headers)
        h["Content-Type"] = content_type
        r = self._http(self._requests.post, f"{self.base}{path}", data=body.encode(),
                       headers=h, auth=self.auth, timeout=120)
        if r.status_code >= 400:
            raise EngineError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def _sql(self, stmt):
        out = self._post("/sql", stmt, "text/plain")
        for part in (out if isinstance(out, list) else [out]):
            if isinstance(part, dict) and part.get("status") == "ERR":
                raise EngineError(str(part.get("result"))[:300])
        return out

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        for t in (edge_label, primary):
            try:
                self._sql(f"REMOVE TABLE IF EXISTS {t};")
            except EngineError:
                pass
        for n in g.nodes.values():
            props = ", ".join(f"{k}='{v}'" for k, v in n.props)
            sep = ", " if props else ""
            self._sql(f"CREATE {primary}:{n.id} SET eid='{n.id}'{sep}{props};")
        for e in g.edges.values():
            lbl = sorted(e.labels)[0] if e.labels else "REL"
            self._sql(f"RELATE {primary}:{e.src}->{lbl}->{primary}:{e.dst} "
                      f"SET eid='{e.id}';")

    def run(self, q: str) -> Answer:
        out = self._post("/gql", q, "text/plain")
        parts = out if isinstance(out, list) else [out]
        rows = []
        for part in parts:
            if isinstance(part, dict) and part.get("status") == "ERR":
                raise EngineError(str(part.get("result"))[:300])
            for r in (part.get("result") or []):
                rows.append((r.get("s"), r.get("t")))
        return _counter(rows, None)


class SpannerAdapter:
    """Google Spanner Graph, through the free Cloud Spanner emulator.

    The emulator runs offline with no account, no IAM and no TLS, and since v1.5.30 it
    serves property graphs. It is the only free local engine in the matrix that ships
    the standard's path modes and selectors together, and the vendor publishes a
    per-feature ISO conformance table, so its row can be read against its own claim.

    Spanner's property-graph labels are fixed by DDL, so one database is created per
    (node label, edge label) pair the fixtures use -- two pairs in all -- and rows are
    cleared between fixtures rather than the schema rebuilt.
    """

    name = "spanner"
    dialect = "gql"

    _COLS = ("eid", "name", "tag", "owner")

    def __init__(self, project="gpml", instance="gpml-inst", host=None):
        import os as _os
        from google.cloud import spanner
        if host:
            _os.environ["SPANNER_EMULATOR_HOST"] = host
        _os.environ.setdefault("SPANNER_EMULATOR_HOST", "localhost:9010")
        _os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        self._spanner = spanner
        self._client = spanner.Client(project=project)
        self._instance = self._client.instance(
            instance,
            configuration_name=f"projects/{project}/instanceConfigs/emulator-config",
            node_count=1)
        if not self._instance.exists():
            self._instance.create().result(180)
        self._dbs: dict[tuple, object] = {}
        self._db = None
        self.version = self._version()

    def _version(self):
        # The emulator reports no version over the API. The image tag is the fact, and
        # the caller sets it; recording "emulator" alone would be a version string that
        # cannot be traced to an image.
        import os as _os
        return f"cloud-spanner-emulator {_os.environ.get('CF_SPANNER_TAG', '1.5.58')}"

    def _ddl(self, primary: str, edge_label: str):
        cols = ", ".join(f"{c} STRING(64)" for c in self._COLS[1:])
        return [
            f"CREATE TABLE {primary} (eid STRING(64) NOT NULL, {cols}) "
            f"PRIMARY KEY (eid)",
            f"CREATE TABLE {edge_label} (src STRING(64) NOT NULL, "
            f"eid STRING(64) NOT NULL, dst STRING(64) NOT NULL, "
            f"FOREIGN KEY (src) REFERENCES {primary} (eid), "
            f"FOREIGN KEY (dst) REFERENCES {primary} (eid)) PRIMARY KEY (src, eid)",
            f"CREATE PROPERTY GRAPH g "
            f"NODE TABLES ({primary} KEY (eid) LABEL {primary} PROPERTIES ALL COLUMNS) "
            f"EDGE TABLES ({edge_label} KEY (src, eid) "
            f"SOURCE KEY (src) REFERENCES {primary} (eid) "
            f"DESTINATION KEY (dst) REFERENCES {primary} (eid) "
            f"LABEL {edge_label} PROPERTIES ALL COLUMNS)",
        ]

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        key = (primary, edge_label)
        if key not in self._dbs:
            dbid = f"g-{primary.lower()}-{edge_label.lower()}"[:30]
            db = self._instance.database(dbid, ddl_statements=self._ddl(primary, edge_label))
            if not db.exists():
                db.create().result(300)
            self._dbs[key] = db
        self._db = self._dbs[key]
        self._primary, self._edge = primary, edge_label
        with self._db.batch() as b:
            b.delete(table=edge_label, keyset=self._spanner.KeySet(all_=True))
            b.delete(table=primary, keyset=self._spanner.KeySet(all_=True))
        with self._db.batch() as b:
            b.insert(table=primary, columns=self._COLS,
                     values=[(n.id,) + tuple(dict(n.props).get(c) for c in self._COLS[1:])
                             for n in g.nodes.values()])
            b.insert(table=edge_label, columns=("src", "eid", "dst"),
                     values=[(e.src, e.id, e.dst) for e in g.edges.values()])

    def run(self, q: str) -> Answer:
        try:
            with self._db.snapshot() as snap:
                rows = [tuple(r) for r in snap.execute_sql(f"GRAPH g {q}")]
        except Exception as ex:
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        return _counter(rows, None)


class IsolatedKuzuAdapter:
    """A Kuzu-API engine driven in its own interpreter.

    LadybugDB is the live MIT fork of Kuzu, whose own row is frozen: 0.11.3 is the
    final release and the repository is archived. Both wheels are built from the same
    C++ sources and both export a pybind11 type named `Database`, and pybind11's type
    registry is global to the interpreter -- so whichever imports second raises
    "type Database is already registered", falls back to a C API shared library the
    wheel does not ship, and reports a misleading "could not find lbug C API shared
    library". Keeping both rows therefore means keeping them in separate processes.

    The worker is src/_engine_worker.py and the protocol is newline-delimited JSON.
    """

    dialect = "cypher"

    def __init__(self, workdir: str, module: str = "ladybug", name: str = "ladybugdb",
                 python: str | None = None):
        import json as _json
        import os as _os
        import subprocess
        import sys as _sys
        self._json = _json
        self.name = name
        self.workdir = workdir
        _os.makedirs(workdir, exist_ok=True)
        worker = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                               "_engine_worker.py")
        self._proc = subprocess.Popen(
            [python or _sys.executable, "-u", worker, module, workdir],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
        self.version = self._call({"op": "version"})["version"]

    def _call(self, msg):
        if self._proc.poll() is not None:
            raise EngineUnavailable(f"{self.name} worker exited "
                                    f"with code {self._proc.returncode}")
        self._proc.stdin.write(self._json.dumps(msg) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise EngineUnavailable(f"{self.name} worker closed the pipe")
        out = self._json.loads(line)
        if not out.get("ok"):
            raise EngineError(out.get("error", "unknown worker error"))
        return out

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        self._call({
            "op": "load", "primary": primary, "edge_label": edge_label,
            "nodes": [{"id": n.id, "labels": sorted(n.labels), "props": dict(n.props)}
                      for n in g.nodes.values()],
            "edges": [{"id": e.id, "src": e.src, "dst": e.dst}
                      for e in g.edges.values()],
        })

    def run(self, q: str) -> Answer:
        return _counter([tuple(r) for r in self._call({"op": "run", "q": q})["rows"]],
                        None)

    def close(self):
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=10)
        except Exception:
            self._proc.kill()


class GrafeoAdapter:
    """Grafeo, over its HTTP query endpoint.

    A small Apache-2.0 engine that ships the standard's path modes and selectors. It is
    in the matrix because it is the second engine measured that implements the
    restrictors, and the first that is not backed by a large vendor -- which is the
    difference between "a big team can do this" and "this is implementable".

    Its release notes describe fixing silent wrong results in other clauses, so its own
    maintainers treat that failure mode as live. A conformance suite is worth most
    against a target like that.
    """

    name = "grafeo"
    dialect = "cypher"

    def __init__(self, base="http://localhost:7475"):
        import requests
        self._requests = requests
        self.base = base.rstrip("/")
        self.version = self._version()

    def _version(self):
        try:
            r = self._requests.get(f"{self.base}/health", timeout=10)
            if r.ok:
                v = r.json().get("version")
                if v:
                    return f"grafeo {v}"
        except Exception:
            pass
        return "grafeo unknown"


    def _http(self, fn, *a, **kw):
        """Run an HTTP call, telling a refusal apart from a dead engine.

        A 4xx or 5xx with a body is the engine answering: it parsed the request and
        said no. A transport failure -- connection reset, closed socket, timeout -- is
        the engine not being there, which is not a verdict about the query.
        """
        try:
            return fn(*a, **kw)
        except Exception as ex:
            if type(ex).__name__ in ("ConnectionError", "ReadTimeout", "Timeout",
                                     "ChunkedEncodingError", "ConnectTimeout"):
                raise EngineUnavailable(f"{self.name}: {type(ex).__name__}: "
                                        f"{str(ex)[:160]}") from ex
            raise

    def _query(self, q):
        r = self._http(self._requests.post, f"{self.base}/query",
                       json={"query": q}, timeout=120)
        if r.status_code >= 400:
            raise EngineError(f"HTTP {r.status_code}: {r.text[:300]}")
        body = r.json()
        if isinstance(body, dict) and body.get("error"):
            raise EngineError(str(body["error"])[:300])
        return body

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        # An ill-formed unbounded pattern OOM-kills this engine
        # (reproducers/grafeo-walk-unbounded-oom.py), so the container is set to
        # restart and `load` waits for it to come back. The wait is here and not in
        # `run`: a query that kills the engine must still be recorded as having killed
        # it, not retried until it looks like a refusal.
        for attempt in range(30):
            try:
                self._query("RETURN 1")
                break
            except EngineUnavailable:
                import time as _time
                _time.sleep(2)
        # No DDL: the store is schemaless, so the fixture is cleared and rewritten.
        try:
            self._query("MATCH (n) DETACH DELETE n")
        except EngineError:
            self._query("MATCH (n) DELETE n")
        for n in g.nodes.values():
            labels = "".join(f":{l}" for l in sorted(n.labels))
            props = ", ".join(f"{k}: '{v}'" for k, v in n.props)
            sep = ", " if props else ""
            self._query(f"CREATE (x{labels} {{eid: '{n.id}'{sep}{props}}})")
        for e in g.edges.values():
            lbl = sorted(e.labels)[0] if e.labels else "REL"
            self._query(f"MATCH (a),(b) WHERE a.eid='{e.src}' AND b.eid='{e.dst}' "
                        f"CREATE (a)-[:{lbl} {{eid:'{e.id}'}}]->(b)")

    def run(self, q: str) -> Answer:
        body = self._query(q)
        cols = body.get("columns") or []
        rows = []
        for r in body.get("rows") or []:
            if len(r) >= 2:
                rows.append((r[0], r[1]))
        return _counter(rows, None)
