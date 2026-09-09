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
    pass


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
    name = "kuzu"
    dialect = "cypher"
    version = None

    def __init__(self, workdir: str):
        import kuzu
        self._kuzu = kuzu
        self.workdir = workdir
        self.version = kuzu.__version__

    def load(self, g: PropertyGraph, primary: str, edge_label: str):
        import shutil, os, uuid
        path = os.path.join(self.workdir, f"kuzu-{uuid.uuid4().hex}")
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
        # Kuzu 0.11 exposes no warning or notification channel on a query result.
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
        try:
            v = self._post("RETURN 1")["engine_version"]
        except Exception:
            return "unknown"
        return f"samyama {v} ({self.build})"

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
