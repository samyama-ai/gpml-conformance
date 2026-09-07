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
    pairs: Counter          # multiset of (s, t)
    raw_rows: int


def _counter(rows) -> Answer:
    c = Counter()
    for r in rows:
        c[(str(r[0]), str(r[1]))] += 1
    return Answer(c, len(rows))


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
        return _counter(rows)


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
        return _counter(rows)


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
                rows = [tuple(r.values()) for r in s.run(q)]
        except Exception as ex:
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        return _counter(rows)


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
            self.cur.execute(wrapped)
            rows = self.cur.fetchall()
        except Exception as ex:
            try:
                self.conn.rollback()
            except Exception:
                pass
            raise EngineError(f"{type(ex).__name__}: {ex}") from ex
        return _counter([(str(a).strip('"'), str(b).strip('"')) for a, b in rows])
