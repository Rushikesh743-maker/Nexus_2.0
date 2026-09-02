import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Network, Maximize2, HelpCircle, Info, UserSearch, FolderOpen, Eye, MapPin } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Avatar } from '@/components/ui/Avatar';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EntityExplorer } from '@/components/intelligence/EntityExplorer';
import { EntityDetailsDrawer } from '@/components/intelligence/EntityDetailsDrawer';
import { RelationshipWhyModal } from '@/components/intelligence/RelationshipWhyModal';
import { NetworkGraph } from '@/components/graph/NetworkGraph';
import { GraphControls } from '@/components/graph/GraphControls';
import { useInvestigation } from './InvestigationLayout';
import { evidenceService, intelligenceService } from '@/services';
import { ENTITY_TYPES, ENTITY_RESOLUTION, RELATIONSHIP_TYPES } from '@/lib/constants';
import { useNavigate } from 'react-router-dom';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

export function NetworkPage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Network`);
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [error, setError] = useState(null);
  const [fitKey, setFitKey] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();

  // Graph control state
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [relFilter, setRelFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('all');
  const [includeEvidence, setIncludeEvidence] = useState(false);
  const [highlightMode, setHighlightMode] = useState(null);
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [hiddenIds, setHiddenIds] = useState(() => new Set());
  const [selectedId, setSelectedId] = useState(null);

  const [drawerEntity, setDrawerEntity] = useState(null);
  const [whyRelationship, setWhyRelationship] = useState(null);

  useEffect(() => {
    let active = true;
    setData(null);
    setSelectedId(null);
    setDrawerEntity(null);
    setWhyRelationship(null);
    setError(null);
    setSearch('');
    setTypeFilter('all');
    setRelFilter('all');
    setDateFilter('all');
    setIncludeEvidence(false);
    setHighlightMode(null);
    setExpandedIds(new Set());
    setHiddenIds(new Set());
    intelligenceService
      .getNetwork(investigation.id, { includeEvidence: true })
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e));
    evidenceService
      .list(investigation.id)
      .then((r) => active && setEvidence(r.items))
      .catch(() => active && setEvidence([]));
    return () => {
      active = false;
    };
  }, [investigation.id]);

  // Deep link: /network?entity=<id> selects a node and opens its details.
  useEffect(() => {
    const eid = searchParams.get('entity');
    if (eid && data?.entities.some((e) => e.id === eid)) {
      setSelectedId(eid);
      setDrawerEntity(data.entities.find((e) => e.id === eid));
      setSearchParams({}, { replace: true });
    }
  }, [data, searchParams, setSearchParams]);

  const entitiesById = useMemo(() => Object.fromEntries((data?.entities || []).map((e) => [e.id, e])), [data]);

  const eventsByEntity = useMemo(() => {
    const map = {};
    (data?.events || []).forEach((event) =>
      (event.entityIds || []).forEach((id) => {
        (map[id] = map[id] || []).push(event.datetime);
      })
    );
    return map;
  }, [data]);

  const maxEventDate = useMemo(() => {
    const times = (data?.events || []).map((e) => new Date(e.datetime).getTime());
    return times.length ? Math.max(...times) : Date.now();
  }, [data]);

  const hubIds = useMemo(() => {
    if (!data) return new Set();
    const sorted = [...data.entities].sort((a, b) => (b.connections || 0) - (a.connections || 0));
    return new Set(sorted.slice(0, 12).map((e) => e.id));
  }, [data]);

  const selected = selectedId ? entitiesById[selectedId] || null : null;

  const highlightIds = useMemo(() => {
    if (!data || !highlightMode) return null;
    if (highlightMode === 'hubs') return new Set(data.insights.hubs.map((h) => h.id));
    if (highlightMode === 'bridges') return new Set(data.insights.bridges.map((h) => h.id));
    if (highlightMode === 'crossCase') return new Set(data.insights.crossCase.map((h) => h.id));
    if (highlightMode.startsWith('cluster:')) {
      const cluster = data.insights.clusters.find((c) => highlightMode === `cluster:${c.id}`);
      return cluster ? new Set(cluster.entityIds) : null;
    }
    return null;
  }, [data, highlightMode]);

  const displayRelationships = useMemo(() => {
    if (!data) return [];
    const base = relFilter === 'all' ? data.relationships : data.relationships.filter((r) => r.type === relFilter);
    return base;
  }, [data, relFilter]);

  const displayEvidenceNodes = includeEvidence && relFilter === 'all' ? data?.evidenceNodes || [] : [];
  const displayEvidenceEdges = includeEvidence && relFilter === 'all' ? data?.evidenceEdges || [] : [];

  const visibleIds = useMemo(() => {
    if (!data) return null;
    const base = data.entities.length <= 14
      ? new Set(data.entities.map((e) => e.id))
      : new Set([...hubIds, ...expandedIds]);
    const term = search.trim().toLowerCase();
    const cutoff = dateFilter === 'all' ? 0 : maxEventDate - parseInt(dateFilter, 10) * 24 * 60 * 60 * 1000;

    return new Set([
      ...data.entities
        .filter((e) => {
          if (hiddenIds.has(e.id)) return false;
          if (e.type === 'evidence') return true;
          if (!base.has(e.id)) return false;
          if (typeFilter !== 'all' && e.type !== typeFilter) return false;
          if (term && ![e.name, ...(e.aliases || []), e.role || ''].join(' ').toLowerCase().includes(term)) return false;
          if (cutoff) {
            const times = eventsByEntity[e.id] || [];
            if (!times.some((t) => new Date(t).getTime() >= cutoff)) return false;
          }
          return true;
        })
        .map((e) => e.id),
      // Evidence graph nodes bypass entity filters; the toggle governs them.
      ...(includeEvidence && relFilter === 'all' ? (data.evidenceNodes || []).map((n) => n.id) : []),
    ]);
  }, [data, hiddenIds, hubIds, expandedIds, typeFilter, search, dateFilter, eventsByEntity, maxEventDate, includeEvidence, relFilter]);

  const selectedLocations = useMemo(() => {
    if (!data || !selectedId) return 0;
    return data.relationships.filter(
      (r) => (r.sourceId === selectedId || r.targetId === selectedId) &&
        (entitiesById[r.sourceId === selectedId ? r.targetId : r.sourceId]?.type === 'address')
    ).length;
  }, [data, selectedId, entitiesById]);

  const connections = useMemo(() => {
    if (!data || !selectedId) return [];
    return data.relationships
      .filter((r) => r.sourceId === selectedId || r.targetId === selectedId)
      .map((r) => ({
        rel: r,
        other: entitiesById[r.sourceId === selectedId ? r.targetId : r.sourceId],
      }))
      .filter((c) => c.other);
  }, [data, selectedId, entitiesById]);

  const openDetails = (entity) => {
    setSelectedId(entity.id);
    setDrawerEntity(entity);
  };

  const expandConnections = () => {
    if (!selectedId || !data) return;
    setExpandedIds((current) => {
      const next = new Set(current);
      data.relationships.forEach((r) => {
        if (r.sourceId === selectedId) next.add(r.targetId);
        if (r.targetId === selectedId) next.add(r.sourceId);
      });
      (data.evidenceEdges || []).forEach((r) => {
        if (r.sourceId === selectedId) next.add(r.targetId);
      });
      return next;
    });
  };

  const hideConnections = () => {
    if (!selectedId || !data) return;
    setHiddenIds((current) => {
      const next = new Set(current);
      data.relationships.forEach((r) => {
        if (r.sourceId === selectedId) next.add(r.targetId);
        if (r.targetId === selectedId) next.add(r.sourceId);
      });
      return next;
    });
  };

  const resetView = () => {
    setSearch('');
    setTypeFilter('all');
    setRelFilter('all');
    setDateFilter('all');
    setHighlightMode(null);
    setExpandedIds(new Set());
    setHiddenIds(new Set());
    setFitKey((k) => k + 1);
  };

  if (error) {
    return <ErrorState title="Could not load the network" description={error.message} onRetry={() => setFitKey((k) => k + 1)} />;
  }

  if (!data) return <PageLoader label="Computing network layout…" />;

  if (data.entities.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={Network}
          title="No entities mapped for this case yet"
          description="Entities are extracted by the backend ingestion pipeline and plotted here with their relationships. Connect the API to populate this view."
        />
      </Card>
    );
  }

  const visibleCount = visibleIds ? visibleIds.size : 0;

  return (
    <div className="space-y-6">
      {/* Entity Explorer catalog */}
      <EntityExplorer entities={data.entities} selectedId={selectedId} onSelect={openDetails} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Graph */}
        <Card className="overflow-hidden xl:col-span-2">
          <GraphControls
            search={search}
            onSearch={setSearch}
            typeFilter={typeFilter}
            onTypeFilter={setTypeFilter}
            relFilter={relFilter}
            onRelFilter={setRelFilter}
            dateFilter={dateFilter}
            onDateFilter={setDateFilter}
            includeEvidence={includeEvidence}
            onIncludeEvidence={setIncludeEvidence}
            insights={data.insights}
            highlightMode={highlightMode}
            onHighlightMode={setHighlightMode}
            hasSelection={Boolean(selectedId)}
            onExpand={expandConnections}
            onHide={hideConnections}
            onReset={resetView}
            onFit={() => setFitKey((k) => k + 1)}
          />

          <NetworkGraph
            key={fitKey}
            entities={data.entities}
            relationships={displayRelationships}
            evidenceNodes={displayEvidenceNodes}
            evidenceEdges={displayEvidenceEdges}
            visibleIds={visibleIds}
            highlightIds={highlightIds}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onEdgeSelect={setWhyRelationship}
            height="h-[440px]"
          />

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100 px-4 py-2.5">
            {Object.entries(RELATIONSHIP_TYPES)
              .filter(([key]) => key !== 'family')
              .map(([key, meta]) => (
                <span key={key} className="flex items-center gap-1.5 text-[11px] font-medium text-navy-400">
                  <span className="h-1.5 w-4 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
                  {meta.label}
                </span>
              ))}
            <span className="ml-auto text-[11px] text-navy-300">
              {visibleCount} of {data.entities.length} nodes · click an edge for “Why this connection?”
            </span>
          </div>
        </Card>

        {/* Side panel */}
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Node panel"
              subtitle={selected ? undefined : 'Click a node or edge to inspect it.'}
              actions={!selected && <UserSearch className="h-4 w-4 text-navy-200" aria-hidden />}
            />
            <CardBody>
              {selected ? (
                <div className="space-y-4">
                  <div className="flex items-start gap-3">
                    <Avatar name={selected.name} size="md" />
                    <div className="min-w-0 flex-1">
                      <h3 className="text-[15px] font-semibold text-navy-900">{selected.name}</h3>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <Badge variant="neutral">{(ENTITY_TYPES[selected.type] || ENTITY_TYPES.asset).label}</Badge>
                        <Badge variant={(ENTITY_RESOLUTION[selected.resolution] || ENTITY_RESOLUTION.unverified).variant} dot>
                          {(ENTITY_RESOLUTION[selected.resolution] || ENTITY_RESOLUTION.unverified).label}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  <dl className="grid grid-cols-4 gap-2">
                    <StatTile label="Connections" value={selected.connections ?? 0} />
                    <StatTile label="Evidence" value={selected.evidenceCount ?? '—'} />
                    <StatTile label="Events" value={(eventsByEntity[selected.id] || []).length} />
                    <StatTile label="Locations" value={selectedLocations} />
                  </dl>

                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" icon={Eye} className="flex-1" onClick={() => setDrawerEntity(selected)}>
                      View Details
                    </Button>
                    <Button variant="outline" size="sm" icon={FolderOpen} className="flex-1" onClick={() => navigate('evidence')}>
                      View Evidence
                    </Button>
                  </div>

                  <div>
                    <h4 className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">
                      Connections ({connections.length})
                    </h4>
                    <ul className="mt-2 space-y-1.5">
                      {connections.map(({ rel, other }) => {
                        const typeMeta = RELATIONSHIP_TYPES[rel.type] || RELATIONSHIP_TYPES.associate;
                        return (
                          <li key={rel.id} className="rounded-lg border border-slate-100 p-2">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setSelectedId(other.id)}
                                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                              >
                                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: typeMeta.color }} aria-hidden />
                                <span className="truncate text-[12.5px] font-medium text-navy-700 hover:text-teal-700">{other.name}</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => setWhyRelationship(rel)}
                                aria-label={`Why this connection with ${other.name}?`}
                                title="Why this connection?"
                                className="rounded p-1 text-navy-300 transition-colors hover:bg-slate-100 hover:text-teal-700"
                              >
                                <HelpCircle className="h-4 w-4" aria-hidden />
                              </button>
                            </div>
                          </li>
                        );
                      })}
                      {connections.length === 0 && <li className="text-[12px] text-navy-300">No visible links (try Expand connections).</li>}
                    </ul>
                  </div>
                </div>
              ) : (
                <p className="py-2 text-[13px] leading-relaxed text-navy-400">
                  Select a node to see its profile and actions. Use <strong className="font-semibold text-navy-600">Expand connections</strong> to
                  grow the graph from a node, or an edge to ask “Why this connection?”.
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardBody className="flex items-start gap-3 py-3.5">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" aria-hidden />
              <p className="text-[12px] leading-relaxed text-navy-400">
                Highlights are simple structural observations (link counts, connected groups) to help analysts orient — they are
                not risk scores. Node dots show identity resolution. Evidence nodes appear when “Include evidence files” is on;
                their links are placeholders pending the extraction pipeline.
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Most connected" subtitle="Ranked by relationship count." />
            <CardBody className="space-y-2">
              {[...data.entities]
                .filter((e) => e.type !== 'evidence')
                .sort((a, b) => (b.connections || 0) - (a.connections || 0))
                .slice(0, 5)
                .map((entity) => {
                  const resolution = ENTITY_RESOLUTION[entity.resolution] || ENTITY_RESOLUTION.unverified;
                  return (
                    <button
                      key={entity.id}
                      type="button"
                      onClick={() => setSelectedId(entity.id)}
                      className={`flex w-full items-center gap-3 rounded-lg border p-2.5 text-left transition-colors ${
                        selectedId === entity.id ? 'border-teal-400 bg-teal-50/40' : 'border-slate-100 hover:bg-slate-50'
                      }`}
                    >
                      <Avatar name={entity.name} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] font-medium text-navy-700">{entity.name}</span>
                        <span className="text-[11px] text-navy-300">{entity.connections} links</span>
                      </span>
                      <Badge variant={resolution.variant}>{resolution.label}</Badge>
                    </button>
                  );
                })}
            </CardBody>
          </Card>

          <Card>
            <CardBody className="flex items-start gap-3 py-3.5">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-navy-300" aria-hidden />
              <p className="text-[12px] leading-relaxed text-navy-400">
                Prefer geography? Open the <button type="button" className="font-medium text-teal-700 hover:underline" onClick={() => navigate('map')}>map view</button> or the{' '}
                <button type="button" className="font-medium text-teal-700 hover:underline" onClick={() => navigate('workspace')}>split-screen workspace</button>.
              </p>
            </CardBody>
          </Card>
        </div>
      </div>

      {/* Entity details drawer */}
      <EntityDetailsDrawer
        open={Boolean(drawerEntity)}
        entity={drawerEntity}
        context={{ ...data, entitiesById }}
        onClose={() => setDrawerEntity(null)}
      />

      {/* Why this connection? */}
      <RelationshipWhyModal
        open={Boolean(whyRelationship)}
        onClose={() => setWhyRelationship(null)}
        relationship={whyRelationship}
        entitiesById={entitiesById}
        evidence={evidence}
        investigationId={investigation.id}
      />
    </div>
  );
}

function StatTile({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 p-2 text-center">
      <p className="text-base font-semibold leading-none text-navy-900">{value ?? '—'}</p>
      <p className="mt-1 text-[9px] font-medium uppercase tracking-wide text-navy-300">{label}</p>
    </div>
  );
}
