"""Confirmed-graph construction for the Stage 3 intelligence engine.

The ONLY data that enters these graphs are confirmed analytical rows:
`entity` and `relationship` (created by the seed or by an investigator
accepting a Stage 2 candidate). Extraction candidates, pending or rejected
review items, and unresolved match suggestions live in separate tables and
never reach the analysis graph — by construction, not by filtering.

Two graphs are built:

* **Case graph** — one case's confirmed entities (node id ``"e{entity_id}"``)
  and relationships. Used for paths, bridges, clusters and metrics.
* **Merged graph** — all cases, where confirmed entities sharing the same
  (entity_type, normalized name) across cases collapse into one node
  (``"m{type}:{name}"``). This is what makes cross-case analysis possible
  and is the definition of a "shared confirmed entity".

Every node and edge carries the metadata needed to explain a finding:
entity/relationship ids, case ids, and the evidence rows that directly
support them (Stage 2 acceptance writes evidence rows whose
``source_reference`` is ``candidate:{id}``; the link candidate →
entity/relationship is read back from the review rows).

The builder is deliberately a pure function over plain records
(``EntityRecord`` / ``RelationshipRecord``) so the engine is unit-testable
without a database; the service layer converts ORM rows into records.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import networkx as nx

# ------------------------------------------------------------------ limits
# Documented analysis limits (perf + safety): traversal is bounded, result
# sets are capped, and no unbounded searches exist in the engine.
MAX_PATH_DEPTH = 4        # maximum hops for path searches
MAX_PATHS = 5             # maximum paths returned per query
MAX_INDIRECT_PAIRS = 10   # cap for hidden-connection findings
MAX_BRIDGES = 10          # cap for bridge-entity findings
MAX_CLUSTERS = 15         # cap for cluster findings
MAX_TOP_ENTITIES = 5      # cap for high-connectivity findings
MIN_ANALYSIS_NODES = 3    # below this the graph is too small to analyze
MIN_ANALYSIS_EDGES = 2


# ------------------------------------------------------------------ records

@dataclass(frozen=True)
class EntityRecord:
    """A confirmed entity row (never a candidate)."""
    id: int
    case_id: int
    entity_type: str
    canonical_name: str


@dataclass(frozen=True)
class RelationshipRecord:
    """A confirmed relationship row (never a candidate)."""
    id: int
    case_id: int
    source_entity_id: int
    target_entity_id: int
    relationship_type: str
    # Stage 2 provenance: the relationship-candidate id this row was
    # accepted from (None for seeded rows). Used to count supporting
    # evidence rows (source_reference "candidate:{id}").
    candidate_id: int | None = None


# ------------------------------------------------------------------- nodes

@dataclass
class NodeInfo:
    node_id: str
    entity_ids: list[int]          # confirmed entity rows behind this node
    entity_type: str
    display_name: str
    case_ids: list[int]
    evidence_ids: list[int] = field(default_factory=list)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence_ids)


@dataclass
class EdgeInfo:
    edge_key: tuple[str, str]      # (node_a, node_b), sorted
    relationship_id: int
    relationship_type: str
    source_entity: str             # display names, for explanations
    target_entity: str
    case_id: int
    evidence_ids: list[int] = field(default_factory=list)
    verification_status: str = "CONFIRMED"

    @property
    def evidence_count(self) -> int:
        return len(self.evidence_ids)


class ConfirmedGraph:
    """A NetworkX graph plus the explainability metadata around it."""

    def __init__(self, graph: nx.Graph, nodes: dict[str, NodeInfo],
                 edges: dict[tuple[str, str], EdgeInfo]):
        self.graph = graph
        self.nodes = nodes
        self.edges = edges

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def is_insufficient(self) -> bool:
        return (self.node_count < MIN_ANALYSIS_NODES
                or self.edge_count < MIN_ANALYSIS_EDGES)


# --------------------------------------------------------------- name keys

def normalize_name(name: str) -> str:
    """Identity key for cross-case matching: casefolded, whitespace-collapsed."""
    return " ".join((name or "").strip().casefold().split())


def entity_identity(etype: str, name: str) -> str:
    """Merged-graph identity: same type + same normalized name across cases."""
    return f"{etype}:{normalize_name(name)}"


def compute_graph_version(entities: list[EntityRecord],
                          relationships: list[RelationshipRecord]) -> str:
    """Deterministic snapshot hash of the confirmed data an analysis ran on.

    Findings store this; when the current hash differs, the finding is
    *stale* (the confirmed data changed) — the UI says so instead of
    silently showing old results. Recomputing is idempotent: same data,
    same hash, no duplicate findings.
    """
    h = hashlib.sha256()
    for e in sorted(entities, key=lambda x: x.id):
        h.update(f"e{e.id}|{e.entity_type}|{normalize_name(e.canonical_name)}\n".encode())
    for r in sorted(relationships, key=lambda x: x.id):
        h.update(f"r{r.id}|{r.relationship_type}|{r.source_entity_id}|{r.target_entity_id}\n".encode())
    return h.hexdigest()[:16]


def merged_reach(case_graph: ConfirmedGraph,
                 merged: ConfirmedGraph) -> dict[str, int]:
    """For each node of the case graph, how many distinct confirmed cases
    contain that entity's identity (type + normalized name). This feeds the
    cross-case term of the bridge score."""
    by_entity: dict[int, int] = {}
    for info in merged.nodes.values():
        for eid in info.entity_ids:
            by_entity[eid] = len(info.case_ids)
    reach: dict[str, int] = {}
    for n, info in case_graph.nodes.items():
        for eid in info.entity_ids:
            reach[n] = max(reach.get(n, 1), by_entity.get(eid, 1))
    return reach


# ----------------------------------------------------------------- builders

def _evidence_index(evidence) -> dict[str, list[int]]:
    """source_reference -> [evidence ids] (one pass, no per-row queries)."""
    index: dict[str, list[int]] = {}
    for ev in evidence:
        ref = ev.source_reference or ""
        index.setdefault(ref, []).append(ev.id)
    return index


def build_case_graph(entities: list[EntityRecord],
                     relationships: list[RelationshipRecord],
                     evidence_index: dict[str, list[int]],
                     accepted_candidates: dict[int, list[int]]) -> ConfirmedGraph:
    """Build one case's confirmed graph.

    ``accepted_candidates`` maps entity_id -> [entity_candidate ids] so a
    node's directly-linked evidence rows can be counted.
    """
    g = nx.Graph()
    nodes: dict[str, NodeInfo] = {}
    for e in entities:
        nid = f"e{e.id}"
        g.add_node(nid)
        nodes[nid] = NodeInfo(
            node_id=nid, entity_ids=[e.id], entity_type=e.entity_type,
            display_name=e.canonical_name, case_ids=[e.case_id],
            evidence_ids=sorted(set(
                i for cid in accepted_candidates.get(e.id, [])
                for i in evidence_index.get(f"candidate:{cid}", []))))

    edges: dict[tuple[str, str], EdgeInfo] = {}
    for r in relationships:
        a, b = f"e{r.source_entity_id}", f"e{r.target_entity_id}"
        if a not in nodes or b not in nodes or a == b:
            continue  # dangling row; never fabricate structure
        g.add_edge(a, b)
        key = tuple(sorted((a, b)))
        if key in edges:
            # A simple graph: several confirmed relationships between the
            # same pair collapse into one edge (the first row represents
            # it); parallel rows are still counted in the case's own
            # relationship totals and remain individually auditable.
            continue
        ev_ids: list[int] = []
        if r.candidate_id is not None:
            ev_ids = list(evidence_index.get(f"candidate:{r.candidate_id}", []))
        edges[key] = EdgeInfo(
            edge_key=key, relationship_id=r.id,
            relationship_type=r.relationship_type,
            source_entity=nodes[a].display_name,
            target_entity=nodes[b].display_name,
            case_id=r.case_id, evidence_ids=ev_ids)
    return ConfirmedGraph(g, nodes, edges)


def build_merged_graph(entities: list[EntityRecord],
                       relationships: list[RelationshipRecord],
                       evidence_index: dict[str, list[int]],
                       accepted_candidates: dict[int, list[int]]) -> ConfirmedGraph:
    """Build the cross-case graph: confirmed entities sharing
    (type, normalized name) across cases merge into one node."""
    merged: dict[str, NodeInfo] = {}
    entity_to_node: dict[int, str] = {}
    g = nx.Graph()
    for e in sorted(entities, key=lambda x: x.id):
        ident = entity_identity(e.entity_type, e.canonical_name)
        nid = f"m{ident}"
        if nid not in merged:
            merged[nid] = NodeInfo(node_id=nid, entity_ids=[], entity_type=e.entity_type,
                                   display_name=e.canonical_name, case_ids=[])
            g.add_node(nid)
        info = merged[nid]
        if e.id not in info.entity_ids:
            info.entity_ids.append(e.id)
        if e.case_id not in info.case_ids:
            info.case_ids.append(e.case_id)
        # node display name: prefer the shortest canonical spelling seen
        if len(e.canonical_name.strip()) < len(info.display_name.strip()):
            info.display_name = e.canonical_name
        entity_to_node[e.id] = nid

    for info in merged.values():
        info.entity_ids.sort()
        info.case_ids.sort()
        info.evidence_ids = sorted(set(
            i for eid in info.entity_ids
            for cid in accepted_candidates.get(eid, [])
            for i in evidence_index.get(f"candidate:{cid}", [])))

    edges: dict[tuple[str, str], EdgeInfo] = {}
    for r in sorted(relationships, key=lambda x: x.id):
        a = entity_to_node.get(r.source_entity_id)
        b = entity_to_node.get(r.target_entity_id)
        if a is None or b is None or a == b:
            continue
        g.add_edge(a, b)
        key = tuple(sorted((a, b)))
        if key in edges:
            continue
        ev_ids: list[int] = []
        if r.candidate_id is not None:
            ev_ids = list(evidence_index.get(f"candidate:{r.candidate_id}", []))
        edges[key] = EdgeInfo(
            edge_key=key, relationship_id=r.id,
            relationship_type=r.relationship_type,
            source_entity=merged[a].display_name,
            target_entity=merged[b].display_name,
            case_id=r.case_id, evidence_ids=ev_ids)
    return ConfirmedGraph(g, merged, edges)
