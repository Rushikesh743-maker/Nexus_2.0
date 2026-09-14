"""Graph intelligence for the platform (Stage 3).

Analyzes the CONFIRMED case graph (confirmed entities + relationships only —
extraction candidates never enter the engine) with NetworkX and produces
explainable, traceable findings: connection paths, bridge entities,
cross-case links, network clusters and connectivity metrics.
"""

from .graph_builder import (  # noqa: F401
    MAX_PATH_DEPTH, MAX_PATHS,
    ConfirmedGraph, EntityRecord, RelationshipRecord,
    build_case_graph, build_merged_graph, compute_graph_version,
    entity_identity, merged_reach, normalize_name,
)
from .path_analysis import PathResult, find_paths, find_indirect_connections  # noqa: F401
from .bridge_analysis import BridgeResult, analyze_bridges  # noqa: F401
from .cluster_analysis import ClusterResult, analyze_clusters  # noqa: F401
from .cross_case_analysis import CrossCaseResult, analyze_cross_case  # noqa: F401
from .metrics import EntityMetrics, compute_metrics, high_connectivity  # noqa: F401
from . import finding_service  # noqa: F401
