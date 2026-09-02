import { useEffect, useMemo, useState } from 'react';
import { Maximize2, Columns2 } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { NetworkGraph } from '@/components/graph/NetworkGraph';
import { GraphControls } from '@/components/graph/GraphControls';
import { InvestigationMap } from '@/components/map/InvestigationMap';
import { EventTimeline } from '@/components/timeline/EventTimeline';
import { EventDetailsModal } from '@/components/timeline/EventDetailsModal';
import { EntityDetailsDrawer } from '@/components/intelligence/EntityDetailsDrawer';
import { RelationshipWhyModal } from '@/components/intelligence/RelationshipWhyModal';
import { useInvestigation } from './InvestigationLayout';
import { evidenceService, intelligenceService } from '@/services';
import { RELATIONSHIP_TYPES } from '@/lib/constants';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

/**
 * Split-screen investigation workspace: network graph + map side by side,
 * shared timeline below. Everything reads from the same case dataset —
 * the NEXUS command-center view.
 */
export function WorkspacePage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Workspace`);

  const [network, setNetwork] = useState(null);
  const [locations, setLocations] = useState([]);
  const [movement, setMovement] = useState({ legs: [] });
  const [evidence, setEvidence] = useState([]);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [fitKey, setFitKey] = useState(0);

  // Lightweight graph controls (compact set)
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [includeEvidence, setIncludeEvidence] = useState(false);

  const [selectedId, setSelectedId] = useState(null);
  const [drawerEntity, setDrawerEntity] = useState(null);
  const [whyRelationship, setWhyRelationship] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([
      intelligenceService.getNetwork(investigation.id, { includeEvidence: true }),
      intelligenceService.getLocations(investigation.id),
      intelligenceService.getMovement(investigation.id),
      evidenceService.list(investigation.id),
    ])
      .then(([networkRes, locs, mov, evr]) => {
        if (!active) return;
        setNetwork(networkRes);
        setLocations(locs);
        setMovement(mov);
        setEvidence(evr.items);
      })
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigation.id, reloadKey]);

  const entitiesById = useMemo(() => Object.fromEntries((network?.entities || []).map((e) => [e.id, e])), [network]);

  const visibleIds = useMemo(() => {
    if (!network) return null;
    const term = search.trim().toLowerCase();
    return new Set([
      ...network.entities
        .filter((e) => {
          if (typeFilter !== 'all' && e.type !== typeFilter) return false;
          if (term && ![e.name, ...(e.aliases || [])].join(' ').toLowerCase().includes(term)) return false;
          return true;
        })
        .map((e) => e.id),
      ...(includeEvidence ? (network.evidenceNodes || []).map((n) => n.id) : []),
    ]);
  }, [network, search, typeFilter, includeEvidence]);

  if (error) return <ErrorState title="Could not load the workspace" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!network) return <PageLoader label="Assembling workspace…" />;

  if (network.entities.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={Columns2}
          title="Nothing to show in the workspace yet"
          description="Once entities, locations and events are extracted for this case, the graph, map and timeline appear here together."
        />
      </Card>
    );
  }

  const events = [...network.events].sort((a, b) => new Date(b.datetime) - new Date(a.datetime));

  return (
    <div className="space-y-4">
      {/* Top: graph + map */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card className="overflow-hidden">
          <GraphControls
            compact
            search={search}
            onSearch={setSearch}
            typeFilter={typeFilter}
            onTypeFilter={setTypeFilter}
            includeEvidence={includeEvidence}
            onIncludeEvidence={setIncludeEvidence}
            hasSelection={false}
            insights={{ clusters: [] }}
            onExpand={() => {}}
            onHide={() => {}}
            onReset={() => {
              setSearch('');
              setTypeFilter('all');
              setIncludeEvidence(false);
              setFitKey((k) => k + 1);
            }}
            onFit={() => setFitKey((k) => k + 1)}
          />
          <NetworkGraph
            key={fitKey}
            entities={network.entities}
            relationships={network.relationships}
            evidenceNodes={includeEvidence ? network.evidenceNodes : []}
            evidenceEdges={includeEvidence ? network.evidenceEdges : []}
            visibleIds={visibleIds}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              if (id && entitiesById[id]) setDrawerEntity(entitiesById[id]);
            }}
            onEdgeSelect={setWhyRelationship}
            height="h-[400px]"
          />
          <div className="flex items-center gap-2 border-t border-slate-100 px-4 py-2 text-[11px] text-navy-300">
            {Object.entries(RELATIONSHIP_TYPES)
              .filter(([key]) => key !== 'family')
              .slice(0, 4)
              .map(([key, meta]) => (
                <span key={key} className="flex items-center gap-1">
                  <span className="h-1.5 w-3 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
                  {meta.label}
                </span>
              ))}
            <span className="ml-auto flex items-center gap-2">
              <Button variant="ghost" size="sm" icon={Maximize2} onClick={() => setFitKey((k) => k + 1)}>
                Fit
              </Button>
              <span>{visibleIds ? visibleIds.size : 0} nodes</span>
            </span>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-navy-900">Location intelligence</p>
            <span className="text-[11px] text-navy-300">
              {locations.length} locations{movement.legs.length ? ` · ${movement.legs.length} movement legs` : ''}
            </span>
          </div>
          {locations.length === 0 ? (
            <EmptyState compact icon={Columns2} title="No mapped locations" description="Locations appear as the pipeline geotags this case." />
          ) : (
            <InvestigationMap locations={locations} movementLegs={movement.legs} className="h-[452px] w-full" />
          )}
        </Card>
      </div>

      {/* Bottom: shared timeline */}
      <Card>
        <CardHeader
          title="Investigation timeline"
          subtitle="Same case data — click any event for details or its linked evidence."
          actions={<span className="text-[11px] text-navy-300">{events.length} events</span>}
        />
        <CardBody>
          {events.length === 0 ? (
            <EmptyState compact icon={Columns2} title="No events recorded yet" />
          ) : (
            <div className="max-h-[360px] overflow-y-auto pr-2 scrollbar-thin">
              <EventTimeline events={events} entityById={entitiesById} onEventClick={setSelectedEvent} />
            </div>
          )}
        </CardBody>
      </Card>

      {/* Shared detail surfaces */}
      <EntityDetailsDrawer
        open={Boolean(drawerEntity)}
        entity={drawerEntity}
        context={{ ...network, entitiesById }}
        onClose={() => setDrawerEntity(null)}
      />
      <RelationshipWhyModal
        open={Boolean(whyRelationship)}
        onClose={() => setWhyRelationship(null)}
        relationship={whyRelationship}
        entitiesById={entitiesById}
        evidence={evidence}
        investigationId={investigation.id}
      />
      <EventDetailsModal event={selectedEvent} entityById={entitiesById} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}
