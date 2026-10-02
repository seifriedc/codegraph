# PROTOTYPE (throwaway): index fixtures, dump graph to data.js
import json, os, duckdb
from pathlib import Path
from codegraph.indexer import Indexer
db = "/tmp/proto_viz.duckdb"
if os.path.exists(db): os.remove(db)
ix = Indexer(db); ix.index(Path("../../tests/fixtures").resolve()); ix.close()
c = duckdb.connect(db, read_only=True)
def rows(q):
    cur = c.execute(q); cols=[d[0] for d in cur.description]
    return [dict(zip(cols, map(lambda v: v if isinstance(v,(int,float,type(None))) else str(v), r))) for r in cur.fetchall()]
nodes = rows("select id,kind,name,qualified_name,file_path,line_start,language from nodes")
edges = rows("select kind,source_id,target_id from edges")
Path("data.js").write_text("window.GRAPH="+json.dumps({"nodes":nodes,"edges":edges})+";")
from collections import Counter
print(len(nodes),len(edges),Counter(n["kind"] for n in nodes),Counter(e["kind"] for e in edges))
