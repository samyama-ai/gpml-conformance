"""Minimal reproducer: DuckPGQ's quantified path pattern is not the standard's.

Three separate symptoms on a two-node directed cycle m -> n -> m:

  1. `{0,0}` returns a one-hop answer. The standard's zero-repetition match leaves
     the path at its start node, so the only answer is (m, m).
  2. `{2,2}` returns nothing, although m -> n -> m is a length-2 path -- and the
     engine's own `{0,2}` finds m at distance 2. That is self-contradictory.
  3. A quantified pattern collapses the multiset of paths to one row per reachable
     endpoint, where SQL/PGQ specifies all paths. The unquantified single-edge
     pattern does keep the multiset, so the two disagree.

Run:  python reproducers/duckpgq-quantifier.py
"""
import duckdb

con = duckdb.connect()
con.execute("INSTALL duckpgq FROM community; LOAD duckpgq;")
print("duckdb", duckdb.__version__, "duckpgq",
      con.execute("SELECT extension_version FROM duckdb_extensions() "
                  "WHERE extension_name='duckpgq'").fetchone()[0])

con.execute("CREATE TABLE N(eid VARCHAR PRIMARY KEY)")
con.execute("INSERT INTO N VALUES ('m'),('n')")
con.execute("CREATE TABLE E(eid VARCHAR, src VARCHAR, dst VARCHAR)")
con.execute("INSERT INTO E VALUES ('e1','m','n'),('e2','n','m')")
con.execute("""CREATE PROPERTY GRAPH g VERTEX TABLES (N)
  EDGE TABLES (E SOURCE KEY (src) REFERENCES N (eid)
                 DESTINATION KEY (dst) REFERENCES N (eid));""")


def q(lo, hi):
    return con.execute(
        f"FROM GRAPH_TABLE(g MATCH (x:N)-[e:E]->{{{lo},{hi}}}(y:N) WHERE x.eid='m' "
        f"COLUMNS (y.eid AS t)) SELECT t, count(*) GROUP BY t ORDER BY t").fetchall()


for lo, hi in [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]:
    print(f"  {{{lo},{hi}}}  {q(lo, hi)}")

print("\n1. {0,0} should be [('m', 1)] -- the zero-length path. Observed:", q(0, 0))
print("2. {2,2} should be [('m', 1)] -- m,e1,n,e2,m. Observed:", q(2, 2))
print("   yet {0,2} does find m at distance 2:", q(0, 2))
