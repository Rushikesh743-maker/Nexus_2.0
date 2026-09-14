"""
Graph storage adapters.

The prototype computes on NetworkX (in-process, over the relational data),
which is the whole graph-intelligence story: there is no graph database to
install or run. This module is the *export* seam: `GraphStore` defines the
contract, and the same in-memory graph can be written to Cypher or JSON —
without the ingestion, analytics or API layers knowing which.

Two implementations ship:

* `CypherExportStore` - writes a .cypher script. Needs nothing installed; the
  output can be loaded into any Cypher-compatible tool (Neo4j Desktop, Aura,
  ...) if you ever want one — NEXUS itself never requires a graph server.
* `JsonExportStore` - a plain dump, useful for handing the graph to another
  tool or diffing two runs.

Property naming matches the in-memory model exactly, so a Cypher query written
against the export reads the same as the Python.
"""

from __future__ import annotations

import json
from datetime import datetime

SCALAR = (str, int, float, bool, type(None))


def _clean(props: dict) -> dict:
    """Graph-store properties must be scalars or arrays of scalars."""
    out = {}
    for k, v in (props or {}).items():
        if isinstance(v, SCALAR):
            out[k] = v
        elif isinstance(v, (list, tuple)):
            flat = [x for x in v if isinstance(x, SCALAR)]
            if flat:
                out[k] = list(flat)
        elif isinstance(v, dict):
            out[k] = json.dumps(v, ensure_ascii=False)
    return out


class GraphStore:
    name = "base"

    def upsert_node(self, node_id: str, label: str, props: dict): ...
    def upsert_edge(self, a: str, b: str, rel_type: str, props: dict): ...
    def finish(self) -> dict: return {}


# ---------------------------------------------------------------- Cypher

def _lit(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_lit(x) for x in v) + "]"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ") + "'"


def _props(p: dict) -> str:
    return "{" + ", ".join(f"{k}: {_lit(v)}" for k, v in p.items()) + "}"


class CypherExportStore(GraphStore):
    name = "cypher-export"

    def __init__(self, path: str):
        self.path = path
        self.nodes: list[str] = []
        self.edges: list[str] = []
        self.n_nodes = self.n_edges = 0

    def upsert_node(self, node_id, label, props):
        p = _clean({**props, "id": node_id})
        self.nodes.append(f"MERGE (n:{label} {{id: {_lit(node_id)}}}) SET n += {_props(p)};")
        self.n_nodes += 1

    def upsert_edge(self, a, b, rel_type, props):
        p = _clean(props)
        self.edges.append(
            f"MATCH (a {{id: {_lit(a)}}}), (b {{id: {_lit(b)}}}) "
            f"MERGE (a)-[r:{rel_type}]-(b) SET r += {_props(p)};")
        self.n_edges += 1

    def finish(self):
        header = [
            "// Criminal Network Analysis System - graph export",
            f"// generated {datetime.now().isoformat(timespec='seconds')}",
            "// All data is synthetic.",
            "//",
            "// Load:  cat graph.cypher | cypher-shell -u neo4j -p <password>",
            "//",
            "CREATE CONSTRAINT entity_id IF NOT EXISTS",
            "  FOR (n:Person) REQUIRE n.id IS UNIQUE;",
            "",
        ]
        useful = [
            "",
            "// ---- equivalents of the analytics this prototype runs in Python ----",
            "//",
            "// Shortest path between two subjects:",
            "//   MATCH p = shortestPath((a:Person {label:'Devendra Kumar Rathi'})",
            "//                          -[*..6]-(b:Person {label:'Vikram Sethi'}))",
            "//   RETURN p;",
            "//",
            "// Influence (requires the Graph Data Science library):",
            "//   CALL gds.graph.project('net', 'Person', {CALLED: {orientation:'UNDIRECTED'}});",
            "//   CALL gds.pageRank.stream('net') YIELD nodeId, score",
            "//   RETURN gds.util.asNode(nodeId).label AS name, score ORDER BY score DESC;",
            "//",
            "// Communities:",
            "//   CALL gds.louvain.stream('net') YIELD nodeId, communityId",
            "//   RETURN communityId, collect(gds.util.asNode(nodeId).label);",
        ]
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(header + self.nodes + [""] + self.edges + useful) + "\n")
        return {"store": self.name, "path": self.path,
                "nodes": self.n_nodes, "edges": self.n_edges}


# ------------------------------------------------------------------ JSON

class JsonExportStore(GraphStore):
    name = "json-export"

    def __init__(self, path: str):
        self.path = path
        self.data = {"nodes": [], "edges": []}

    def upsert_node(self, node_id, label, props):
        self.data["nodes"].append({"id": node_id, "label_type": label, **_clean(props)})

    def upsert_edge(self, a, b, rel_type, props):
        self.data["edges"].append({"from": a, "to": b, "type": rel_type, **_clean(props)})

    def finish(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        return {"store": self.name, "path": self.path,
                "nodes": len(self.data["nodes"]), "edges": len(self.data["edges"])}


# ------------------------------------------------------------------ pump

def export_graph(case_graph, store: GraphStore) -> dict:
    """Walk the in-memory graph into any store. The only place that knows both."""
    for nid, d in case_graph.G.nodes(data=True):
        label = (d.get("type") or "Entity").title().replace("_", "")
        props = {k: v for k, v in d.items() if k != "type"}
        props["entity_type"] = d.get("type")
        store.upsert_node(nid, label, props)
    for a, b, d in case_graph.G.edges(data=True):
        rel = (d["types"][0] if d.get("types") else "RELATED_TO")
        props = {
            "types": d.get("types"), "weight": round(d.get("weight", 0), 4),
            "confidence": d.get("confidence"), "observations": d.get("observations"),
            "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
            "independent_sources": sorted({s["source_type"] for s in d.get("sources", [])}),
            "source_ids": sorted({s["source_id"] for s in d.get("sources", [])}),
            "evidence": " | ".join(s.get("evidence", "") for s in d.get("sources", [])[:3]),
        }
        store.upsert_edge(a, b, rel, props)
    return store.finish()


def describe_backends() -> dict:
    return {
        "active": "networkx (in-process, over Supabase/Postgres relational data)",
        "reason": ("graph intelligence is computed in-process with NetworkX; "
                   "there is no graph database to install or run"),
        "available_exports": ["cypher", "json"],
        "swap_path": ("Point export_graph() at another GraphStore, or load the "
                      "Cypher/JSON export. Ingestion, analytics and the API are "
                      "unchanged — only this module knows the export format."),
    }
