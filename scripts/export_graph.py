"""
Export the case graph to Cypher or JSON.

    python3 scripts/export_graph.py              # -> exports/graph.cypher
    python3 scripts/export_graph.py --json       # -> exports/graph.json

The graph is the in-process NetworkX structure built from the relational
data; there is no graph database to connect to. The Cypher output can be
loaded into any Cypher-compatible tool (e.g. Neo4j Desktop/Aura) if you
ever want one — NEXUS itself never requires a graph server.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.graph.build import build_graph                      # noqa: E402
from app.graph.store import (CypherExportStore, JsonExportStore,  # noqa: E402
                             export_graph)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out_dir = os.path.join(ROOT, "exports")
    os.makedirs(out_dir, exist_ok=True)
    g = build_graph()

    if args.json:
        store = JsonExportStore(args.out or os.path.join(out_dir, "graph.json"))
    else:
        store = CypherExportStore(args.out or os.path.join(out_dir, "graph.cypher"))

    print(export_graph(g, store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
