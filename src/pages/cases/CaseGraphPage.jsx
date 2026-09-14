import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Network, Sparkles, X, Search, FileSearch, FileText, User, Clock, MapPin, ZoomIn, ZoomOut } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { NetworkGraph } from '@/components/graph/NetworkGraph';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService, graphService, analysisService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { toGraphNode, toGraphEdge, V1_RELATIONSHIP_CATEGORY } from '@/lib/caseTypes';
import { RELATIONSHIP_TYPES, ENTITY_TYPES } from '@/lib/constants';
import { GraphFindingsPanel } from '@/components/cases/GraphFindingsPanel';
import { PathExplorer } from '@/components/cases/PathExplorer';
import { BridgePanel, ClusterPanel, CrossCasePanel } from '@/components/cases/GraphIntelPanels';

const ENTITY_TYPE_LABEL = {
  person: 'Person',
  organization: 'Organization',
  vehicle: 'Vehicle',
  location: 'Location',
  phone: 'Phone',
  account: 'Account',
  case_reference: 'Case ref',
  other: 'Other',
};

/**
 * Case network — the case's entities and typed relationships, rendered with
 * the shared React Flow component. Data comes straight from the platform
 * API (never the static demo graph): the confirmed entities/relationships
 * plus the case graph payload, which carries per-node evidence counts and
 * per-edge provenance (source document, snippet, evidence link).
 *
 * Deep links: ?entity=<id> selects a node (from the Entities tab and
 * findings), ?relationship=<id> selects an edge (from the Relationships
 * tab). The graph is never detached from its evidence: every confirmed
 * edge shows where it came from, and every entity can open its timeline /
 * map view.
 */
export function CaseGraphPage() {
  const { caseFile: c } = useCaseFile();
  const { data, error, loading, reload } = useCnaResource(
    async () => {
      const [entities, relationships, graph] = await Promise.all([
        caseService.listEntities(c.id),
        caseService.listRelationships(c.id),
        analysisService.getCaseGraph(c.id).catch(() => null),
      ]);
      return { entities, relationships, graph };
    },
    [c.id]
  );

  const [selected, setSelected] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [highlight, setHighlight] = useState(null);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState(null);
  const [relFilter, setRelFilter] = useState(null);
  const [minConfidence, setMinConfidence] = useState(0);
  const [layoutMode, setLayoutMode] = useState('force');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();



  // stage 4: "Show in graph" deep-link from the investigation intelligence
  // page (?highlight=1,2,3&label=…) — applied once on mount.
  useEffect(() => {
    const hl = searchParams.get('highlight');
    if (hl) {
      const ids = hl.split(',').map((s) => Number(s.trim())).filter(Number.isFinite);
      if (ids.length) setHighlight({ ids: new Set(ids), label: searchParams.get('label') || 'Investigation finding' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // stage 7: deep links ?entity= / ?relationship= — select on load.
  useEffect(() => {
    if (!data) return;
    const ent = searchParams.get('entity');
    const rel = searchParams.get('relationship');
    if (ent && data.entities.some((e) => String(e.id) === ent)) setSelected(Number(ent));
    if (rel && data.relationships.some((r) => String(r.id) === rel)) {
      const row = data.relationships.find((r) => String(r.id) === rel);
      setSelectedEdge(toGraphEdge(row));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const highlightIds = highlight ? highlight.ids : null;
  const onHighlight = (ids, label) =>
    setHighlight({ ids: new Set(ids || []), label });
  const onClearHighlight = () => setHighlight(null);

  const { data: metricsData } = useCnaResource(
    () => graphService.getGraphMetrics(c.id), [c.id]);
  const metricsById = useMemo(
    () => Object.fromEntries((metricsData?.metrics || []).map((m) => [m.entity_id, m])),
    [metricsData]
  );

  const degree = useMemo(() => {
    const d = {};
    (data?.relationships || []).forEach((r) => {
      d[r.source_entity_id] = (d[r.source_entity_id] || 0) + 1;
      d[r.target_entity_id] = (d[r.target_entity_id] || 0) + 1;
    });
    return d;
  }, [data]);

  const byId = useMemo(
    () => Object.fromEntries((data?.entities || []).map((e) => [e.id, e])),
    [data]
  );

  // edge provenance from the case graph payload (edge.id = "r<relId>")
  const edgeProvenance = useMemo(() => {
    const map = {};
    for (const e of data?.graph?.edges || []) {
      map[e.id.replace(/^r/, '')] = e;
    }
    return map;
  }, [data]);
  // per-entity evidence count (node ids are "e<entityId>", possibly merged)
  const nodeEvidence = useMemo(() => {
    const map = {};
    for (const n of data?.graph?.nodes || []) {
      for (const eid of n.entity_ids || []) map[eid] = n.evidence_count;
    }
    return map;
  }, [data]);

  const presentRelTypes = useMemo(() => {
    const s = new Set((data?.relationships || []).map((r) => r.relationship_type));
    return [...s].sort();
  }, [data]);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    const visIds = new Set();
    const fEdges = data.relationships
      .filter((r) => {
        if (relFilter && r.relationship_type !== relFilter) return false;
        if (minConfidence > 0 && (r.confidence ?? 0) < minConfidence) return false;
        visIds.add(r.source_entity_id);
        visIds.add(r.target_entity_id);
        return true;
      })
      .map(toGraphEdge);
    // an entity passes the type filter AND (has a visible edge OR no edges at all)
    const fNodes = data.entities
      .filter((e) => {
        if (typeFilter && e.entity_type !== typeFilter) return false;
        return visIds.has(e.id) || (degree[e.id] || 0) === 0;
      })
      .map((e) => toGraphNode(e, degree[e.id] || 0));
    return { nodes: fNodes, edges: fEdges };
  }, [data, typeFilter, relFilter, minConfidence, degree]);

  const selectedEntity = selected ? byId[selected] : null;
  const selectedEdgeRow = selectedEdge
    ? data?.relationships.find((r) => String(r.id) === selectedEdge.id) || null
    : null;
  const entityEdges = useMemo(
    () => (selectedEntity ? data?.relationships.filter((r) => r.source_entity_id === selectedEntity.id || r.target_entity_id === selectedEntity.id) || [] : []),
    [selectedEntity, data]
  );

  // neighbor expansion: 1-hop or 2-hop from the selected entity
  const expandHops = (hops) => {
    if (!selectedEntity) return;
    const rels = data.relationships;
    const reach = new Set([selectedEntity.id]);
    for (let h = 0; h < hops; h++) {
      const frontier = [...reach];
      for (const r of rels) {
        if (frontier.includes(r.source_entity_id)) reach.add(r.target_entity_id);
        if (frontier.includes(r.target_entity_id)) reach.add(r.source_entity_id);
      }
    }
    onHighlight([...reach], `${hops}-hop neighborhood of ${selectedEntity.canonical_name}`);
  };

  const searchMatches = useMemo(() => {
    if (!search.trim()) return [];
    const q = search.trim().toLowerCase();
    return (data?.entities || [])
      .filter((e) => e.canonical_name.toLowerCase().includes(q))
      .slice(0, 6);
  }, [search, data]);

  if (loading && !data) return <PageLoader label="Loading case network…" />;

  if (error && !data) {
    return <ErrorState title="Could not load the case network" description={error.message} onRetry={reload} />;
  }

  if (!data?.entities.length) {
    return (
      <Card>
        <EmptyState
          icon={Network}
          title="No entities in this case"
          description="Entities recorded or extracted into this case will render as a network here. This is built from the case's confirmed data — there is no demo fallback."
        />
      </Card>
    );
  }

  const prov = selectedEdgeRow ? edgeProvenance[String(selectedEdgeRow.id)] : null;

  return (
    <div className="space-y-4">
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <Card className="overflow-hidden">
        {/* filters */}
        <div className="flex flex-wrap items-center gap-2 border-b border-line-soft px-4 py-2.5">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-300" aria-hidden />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search entity…"
              className="w-44 rounded-md border border-line bg-white py-1.5 pl-7 pr-2 text-[12px] text-navy-800 outline-none focus:border-accent"
            />
            {searchMatches.length > 0 && (
              <ul className="absolute left-0 top-full z-10 mt-1 w-56 rounded-md border border-line bg-white py-1 shadow-lg">
                {searchMatches.map((e) => (
                  <li key={e.id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-navy-700 hover:bg-slate-50"
                      onClick={() => { setSelected(e.id); setSearch(''); }}
                    >
                      <span className="h-2 w-2 rounded-full" style={{ background: ENTITY_TYPES[e.entity_type]?.color }} aria-hidden />
                      {e.canonical_name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <select
            value={typeFilter || ''}
            onChange={(e) => setTypeFilter(e.target.value || null)}
            className="rounded-md border border-line bg-white px-2 py-1.5 text-[11.5px] text-navy-700 outline-none"
            aria-label="Filter by entity type"
          >
            <option value="">All entity types</option>
            {Object.keys(ENTITY_TYPE_LABEL).map((t) => (
              <option key={t} value={t}>{ENTITY_TYPE_LABEL[t]}</option>
            ))}
          </select>
          <select
            value={relFilter || ''}
            onChange={(e) => setRelFilter(e.target.value || null)}
            className="rounded-md border border-line bg-white px-2 py-1.5 text-[11.5px] text-navy-700 outline-none"
            aria-label="Filter by relationship type"
          >
            <option value="">All relationship types</option>
            {presentRelTypes.map((t) => (
              <option key={t} value={t}>{t.replace('_', ' ')}</option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-[11px] text-navy-500">
            min confidence
            <input
              type="range" min="0" max="1" step="0.05"
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="w-20"
            />
            <span className="figure w-7">{Math.round(minConfidence * 100)}%</span>
          </label>
          {(typeFilter || relFilter || minConfidence > 0) && (
            <Button variant="ghost" size="sm" icon={X} onClick={() => { setTypeFilter(null); setRelFilter(null); setMinConfidence(0); }}>
              Clear filters
            </Button>
          )}
          <span className="ml-auto text-[11px] text-navy-400">
            <span className="figure">{nodes.length}</span>/{data.entities.length} nodes · <span className="figure">{edges.length}</span>/{data.relationships.length} edges
          </span>
        </div>

        <NetworkGraph
          entities={nodes}
          relationships={edges}
          selectedId={selected}
          onSelect={setSelected}
          onEdgeSelect={setSelectedEdge}
          highlightIds={highlightIds}
          layoutMode={layoutMode}
          onLayoutMode={setLayoutMode}
          height="h-[520px]"
        />
        {highlight && (
          <div className="flex items-center justify-between gap-2 border-t border-line-soft bg-slate-50 px-4 py-2">
            <p className="flex min-w-0 items-center gap-2 text-[12px] text-navy-600">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-teal-600" aria-hidden />
              <span className="truncate">
                Highlighting <span className="font-medium">{highlight.label}</span> — other nodes dimmed
              </span>
            </p>
            <Button variant="ghost" size="sm" icon={X} onClick={onClearHighlight}>
              Clear
            </Button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-4 py-2.5">
          {Object.entries(RELATIONSHIP_TYPES)
            .filter(([key]) => Object.values(V1_RELATIONSHIP_CATEGORY).includes(key))
            .map(([key, meta]) => (
              <span key={key} className="flex items-center gap-1.5 text-[11px] font-medium text-navy-400">
                <span className="h-1.5 w-4 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
                {meta.label}
              </span>
            ))}
        </div>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader
            title="Entity"
            subtitle={selectedEntity ? 'Selected' : 'Select a node'}
            actions={selectedEntity && (
              <Button variant="ghost" size="iconSm" icon={X} onClick={() => setSelected(null)} />
            )}
          />
          {selectedEntity ? (
            <div className="space-y-3 p-4 pt-1">
              <div>
                <p className="text-[14px] font-semibold text-navy-900">{selectedEntity.canonical_name}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge variant="teal">{ENTITY_TYPE_LABEL[selectedEntity.type] || selectedEntity.type}</Badge>
                  <Badge variant="neutral">{degree[selectedEntity.id] || 0} links</Badge>
                  {nodeEvidence[selectedEntity.id] != null && (
                    <Badge variant="info">{nodeEvidence[selectedEntity.id]} evidence</Badge>
                  )}
                </div>
              </div>
              {(selectedEntity.meta?.aliases || selectedEntity.aliases || []).length ? (
                <div>
                  <p className="label-micro">Aliases</p>
                  <p className="mt-1 text-[12.5px] text-navy-600">
                    {(selectedEntity.meta?.aliases || selectedEntity.aliases).join(', ')}
                  </p>
                </div>
              ) : null}
              <div>
                <p className="label-micro">Relationships</p>
                <ul className="mt-1.5 space-y-1.5">
                  {entityEdges.map((r) => {
                    const outgoing = r.source_entity_id === selectedEntity.id;
                    const other = byId[outgoing ? r.target_entity_id : r.source_entity_id];
                    return (
                      <li key={r.id} className="flex items-center justify-between gap-2 text-[12px]">
                        <span className="font-mono text-[10.5px] text-navy-400">
                          {outgoing ? '→' : '←'} {r.relationship_type}
                        </span>
                        <button
                          type="button"
                          className="truncate font-medium text-navy-700 hover:text-navy-950"
                          onClick={() => setSelected(other?.id)}
                        >
                          {other?.canonical_name || '—'}
                        </button>
                      </li>
                    );
                  })}
                  {!entityEdges.length && <li className="text-[12px] text-navy-400">No typed relationships yet.</li>}
                </ul>
              </div>
              {/* cross-page context: the graph is never detached from the record */}
              <div className="flex flex-wrap gap-1.5">
                <Button variant="outline" size="sm" icon={Clock}
                  onClick={() => navigate(`/cases/${c.id}/timeline?entity=${selectedEntity.id}`)}>
                  Timeline
                </Button>
                <Button variant="outline" size="sm" icon={MapPin}
                  onClick={() => navigate(`/cases/${c.id}/map?entity=${selectedEntity.id}`)}>
                  Map
                </Button>
                <Button variant="outline" size="sm" icon={FileText}
                  onClick={() => navigate(`/cases/${c.id}/evidence?entity=${selectedEntity.id}`)}>
                  Evidence
                </Button>
                <Button variant="outline" size="sm" icon={User}
                  onClick={() => navigate(`/cases/${c.id}/entities/${selectedEntity.id}`)}>
                  Profile
                </Button>
                <Button variant="outline" size="sm" icon={ZoomIn} onClick={() => expandHops(1)}>
                  1-hop
                </Button>
                <Button variant="outline" size="sm" icon={ZoomOut} onClick={() => expandHops(2)}>
                  2-hop
                </Button>
              </div>
              {selectedEntity.metadata && Object.keys(selectedEntity.metadata).length > 0 && (
                <div>
                  <p className="label-micro">Recorded details</p>
                  <pre className="mt-1.5 max-h-44 overflow-auto rounded border border-line bg-slate-50 p-2 text-[11px] leading-relaxed text-navy-600">
                    {JSON.stringify(selectedEntity.metadata, null, 2)}
                  </pre>
                </div>
              )}
              {metricsById[selectedEntity.id] && (
                <div>
                  <p className="label-micro">Network intelligence</p>
                  <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px] text-navy-600">
                    <span>Degree <span className="figure text-navy-800">{metricsById[selectedEntity.id].degree}</span></span>
                    <span>Weighted degree <span className="figure text-navy-800">{metricsById[selectedEntity.id].weighted_degree}</span></span>
                    <span>Betweenness <span className="figure text-navy-800">{metricsById[selectedEntity.id].betweenness.toFixed(3)}</span></span>
                    <span>Group size <span className="figure text-navy-800">{metricsById[selectedEntity.id].component_size}</span></span>
                    <span>Cases seen in <span className="figure text-navy-800">{metricsById[selectedEntity.id].cross_case_reach}</span></span>
                    {metricsById[selectedEntity.id].is_articulation_point && (
                      <span className="flex items-center"><Badge variant="warning">articulation point</Badge></span>
                    )}
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-navy-400">
                    Computed from confirmed data; evidence-weighted values are analytical context, not proof.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="p-4 pt-1">
              <p className="text-[12.5px] leading-relaxed text-navy-400">
                Click a node to see its type, aliases, evidence, relationships and how to follow it into the timeline and map.
              </p>
            </div>
          )}
        </Card>

        {selectedEdge && (
          <Card>
            <CardHeader
              title="Relationship"
              subtitle={byId[selectedEdge.sourceId]?.canonical_name || '—'}
              actions={<Button variant="ghost" size="iconSm" icon={X} onClick={() => setSelectedEdge(null)} />}
            />
            <div className="space-y-2 p-4 pt-1 text-[12.5px]">
              <p>
                <span className="font-medium text-navy-800">{byId[selectedEdge.sourceId]?.canonical_name}</span>
                <span className="mx-2 font-mono text-[11px] text-navy-400">{selectedEdge.label}</span>
                <span className="font-medium text-navy-800">{byId[selectedEdge.targetId]?.canonical_name}</span>
              </p>
              {selectedEdge.confidence != null && <p className="text-navy-400">Confidence {Math.round(selectedEdge.confidence * 100)}%</p>}
              {prov?.source_document_name && (
                <div className="rounded-md border border-line bg-slate-50/70 p-2.5">
                  <p className="label-micro mb-1">Supporting evidence</p>
                  <p className="text-[12px] text-navy-700">
                    From <span className="font-medium">{prov.source_document_name}</span>
                    {prov.extraction_method && <span className="figure ml-1 text-[10px] text-navy-400">({prov.extraction_method})</span>}
                  </p>
                  {prov.source_snippet && (
                    <p className="mt-1 border-l-2 border-line pl-2 text-[11.5px] italic text-navy-500">“{prov.source_snippet}”</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {prov.source_evidence_id && (
                      <Button variant="outline" size="sm" icon={FileSearch}
                        onClick={() => navigate(`/cases/${c.id}/evidence?evidence=${prov.source_evidence_id}`)}>
                        View evidence
                      </Button>
                    )}
                    <Button variant="outline" size="sm"
                      onClick={() => navigate(`/cases/${c.id}/documents/${prov.source_document_id}`)}>
                      Open document
                    </Button>
                  </div>
                </div>
              )}
              {!prov?.source_document_name && (
                <p className="text-[11.5px] text-navy-400">
                  Seeded demonstration record — no extraction provenance (the row was seeded, not extracted from an uploaded document).
                </p>
              )}
              {selectedEdgeRow?.metadata && Object.keys(selectedEdgeRow.metadata).length > 0 && (
                <details className="text-[11px] text-navy-400">
                  <summary className="cursor-pointer">Raw metadata</summary>
                  <pre className="mt-1.5 max-h-44 overflow-auto rounded border border-line bg-slate-50 p-2 text-[10.5px] text-navy-600">
                    {JSON.stringify(selectedEdgeRow.metadata, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </Card>
        )}

        <Card>
          <CardHeader title="Entities" subtitle={`${nodes.length} in this case`} />
          <ul className="max-h-64 divide-y divide-line-soft overflow-y-auto">
            {nodes.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => setSelected(n.id)}
                  className={`flex w-full items-center gap-2.5 px-4 py-2 text-left transition-colors hover:bg-slate-50 ${selected === n.id ? 'bg-slate-50' : ''}`}
                >
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: ENTITY_TYPES[n.type]?.color }} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-navy-800">{n.name}</span>
                  <span className="figure text-[10.5px] text-navy-300">{n.connections}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>

    {/* Stage 3: graph intelligence — findings, paths, bridges, clusters, cross-case */}
    <GraphFindingsPanel caseId={c.id} onHighlight={onHighlight} />

    <div className="grid gap-4 xl:grid-cols-2">
      <PathExplorer caseId={c.id} entities={nodes} onHighlight={onHighlight} />
      <BridgePanel caseId={c.id} onHighlight={onHighlight} />
    </div>

    <div className="grid gap-4 xl:grid-cols-2">
      <ClusterPanel caseId={c.id} onHighlight={onHighlight} />
      <CrossCasePanel
        caseId={c.id}
        onHighlight={onHighlight}
        onOpenCase={(id) => navigate(`/cases/${id}/graph`)}
      />
    </div>
    </div>
  );
}
