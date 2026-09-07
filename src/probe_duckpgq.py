"""Characterise what DuckPGQ's bare quantified path pattern actually computes.

Six cells of the map came out DIVERGES for DuckPGQ. Reporting six separate
divergences would be wrong if they share one cause. This probe finds the cause.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import duckdb

con = duckdb.connect()
con.execute("INSTALL duckpgq FROM community; LOAD duckpgq;")
print("duckdb", duckdb.__version__)
print("duckpgq", con.execute(
    "SELECT extension_version FROM duckdb_extensions() WHERE extension_name='duckpgq'"
).fetchall())

con.execute("CREATE TABLE N(eid VARCHAR PRIMARY KEY, name VARCHAR)")
con.execute("INSERT INTO N VALUES ('m','m'),('n','n')")
con.execute("CREATE TABLE E(eid VARCHAR, src VARCHAR, dst VARCHAR)")
con.execute("INSERT INTO E VALUES ('e1','m','n'),('e2','n','m')")
con.execute("""CREATE PROPERTY GRAPH g VERTEX TABLES (N)
  EDGE TABLES (E SOURCE KEY (src) REFERENCES N (eid)
                 DESTINATION KEY (dst) REFERENCES N (eid));""")

print("\n-- directed 2-cycle m<->n, quantifier sweep from m")
for lo, hi in [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (1, 3), (1, 4), (2, 2), (2, 4)]:
    q = (f"FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{{{lo},{hi}}}(y:N) WHERE x.eid='m' "
         f"COLUMNS (y.eid AS t)) SELECT t, count(*) AS c GROUP BY t ORDER BY t")
    try:
        print(f"  {{{lo},{hi}}}  -> {con.execute(q).fetchall()}")
    except Exception as e:
        print(f"  {{{lo},{hi}}}  -> ERROR {str(e)[:90]}")

print("\n-- parallel edges a=>b, does the multiset keep both?")
con.execute("CREATE TABLE N2(eid VARCHAR PRIMARY KEY)")
con.execute("INSERT INTO N2 VALUES ('a'),('b')")
con.execute("CREATE TABLE E2(eid VARCHAR, src VARCHAR, dst VARCHAR)")
con.execute("INSERT INTO E2 VALUES ('p1','a','b'),('p2','a','b')")
con.execute("""CREATE PROPERTY GRAPH g2 VERTEX TABLES (N2)
  EDGE TABLES (E2 SOURCE KEY (src) REFERENCES N2 (eid)
                  DESTINATION KEY (dst) REFERENCES N2 (eid));""")
for pat in ["-[e:E2]->{1,1}", "-[e:E2]->{1,2}", "-[e:E2]->"]:
    q = (f"FROM GRAPH_TABLE(g2 MATCH (x:N2){pat}(y:N2) WHERE x.eid='a' "
         f"COLUMNS (y.eid AS t)) SELECT t, count(*) AS c GROUP BY t")
    try:
        print(f"  {pat:20s} -> {con.execute(q).fetchall()}")
    except Exception as e:
        print(f"  {pat:20s} -> ERROR {str(e)[:90]}")

print("\n-- is the single-edge pattern (no quantifier) a multiset?")
q = ("FROM GRAPH_TABLE(g2 MATCH (x:N2)-[e:E2]->(y:N2) COLUMNS (e.eid AS e)) SELECT e")
print("  ", con.execute(q).fetchall())
