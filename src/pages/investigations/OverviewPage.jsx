import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Users, Share2, FolderOpen, History, MapPin, ArrowRight, HelpCircle } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { StatCard } from '@/components/cards/StatCard';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/LoadingState';
import { EventTimeline } from '@/components/timeline/EventTimeline';
import { ActivityFeed } from '@/components/dashboard/ActivityFeed';
import { RelationshipWhyModal } from '@/components/intelligence/RelationshipWhyModal';
import { useInvestigation } from './InvestigationLayout';
import { analysisService, evidenceService, intelligenceService, investigationService } from '@/services';
import { EVIDENCE_TYPES, EVIDENCE_STATUS, ENTITY_TYPES, ENTITY_RESOLUTION, RELATIONSHIP_TYPES } from '@/lib/constants';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { timeAgo } from '@/lib/utils';

export function OverviewPage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Overview`);
  const navigate = useNavigate();

  const [network, setNetwork] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const [activity, setActivity] = useState(null);
  const [intelligence, setIntelligence] = useState(null);
  const [whyRelationship, setWhyRelationship] = useState(null);

  useEffect(() => {
    let active = true;
    const id = investigation.id;
    Promise.all([
      intelligenceService.getNetwork(id),
      evidenceService.list(id),
      investigationService.getInvestigationActivity(id),
      analysisService.getSummary(id),
    ]).then(([networkRes, evidenceRes, activityRes, summary]) => {
      if (!active) return;
      setNetwork(networkRes);
      setEvidence(evidenceRes.items);
      setActivity(activityRes);
      setIntelligence({ summary });
    });
    return () => {
      active = false;
    };
  }, [investigation.id]);

  const entitiesById = useMemo(
    () => Object.fromEntries((network?.entities || []).map((e) => [e.id, e])),
    [network]
  );

  const stats = investigation.stats;
  const summaryTiles = [
    { icon: Users, label: 'Entities', value: stats.entities, to: 'network', tone: 'violet' },
    { icon: Share2, label: 'Relationships', value: stats.relationships, to: 'network', tone: 'teal' },
    { icon: FolderOpen, label: 'Evidence', value: stats.evidence, to: 'evidence', tone: 'sky' },
    { icon: History, label: 'Events', value: stats.events, to: 'timeline', tone: 'amber' },
    { icon: MapPin, label: 'Locations', value: stats.locations, to: 'map', tone: 'rose' },
  ];

  const recentEntities = (network?.entities || [])
    .filter((e) => e.type === 'person' || e.type === 'organization' || e.type === 'vehicle')
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    .slice(0, 5);

  const importantRelationships = [...(network?.relationships || [])]
    .sort((a, b) => b.strength - a.strength)
    .slice(0, 4);

  const events = network?.events || [];

  return (
    <div className="space-y-6">
      {/* Summary strip — values from the investigation service */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5">
        {summaryTiles.map((tile) => (
          <StatCard key={tile.label} icon={tile.icon} tone={tile.tone} label={tile.label} value={tile.value} to={tile.to} />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Case summary" />
          <CardBody>
            <p className="text-sm leading-relaxed text-navy-600">{investigation.description}</p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="At a glance" />
          <CardBody className="space-y-3 text-[13px]">
            <div className="flex justify-between gap-3">
              <span className="text-navy-400">Case code</span>
              <span className="font-mono font-medium text-navy-700">{investigation.code}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-navy-400">Jurisdiction</span>
              <span className="text-right font-medium text-navy-700">{investigation.jurisdiction || '—'}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-navy-400">Opened</span>
              <span className="font-medium text-navy-700">{investigation.openedAt ? new Date(investigation.openedAt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-navy-400">Last activity</span>
              <span className="font-medium text-navy-700">{timeAgo(investigation.updatedAt)}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-navy-400">Insights</span>
              <span className="font-medium text-navy-700">{stats.insights}</span>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent evidence */}
        <Card>
          <CardHeader
            title="Recent Evidence"
            actions={
              <Link to="evidence" className="flex items-center gap-1 text-[13px] font-medium text-teal-700 hover:text-teal-800">
                All evidence <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            }
          />
          <CardBody className="space-y-3">
            {evidence === null
              ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12" />)
              : evidence.length === 0
                ? <p className="py-6 text-center text-sm text-navy-400">No evidence logged yet.</p>
                : evidence.slice(0, 4).map((ev) => {
                    const typeMeta = EVIDENCE_TYPES[ev.type] || EVIDENCE_TYPES.document;
                    const statusMeta = EVIDENCE_STATUS[ev.status] || EVIDENCE_STATUS.uploaded;
                    return (
                      <Link
                        key={ev.id}
                        to={`evidence?evidence=${ev.id}`}
                        className="flex items-center gap-3 rounded-lg border border-slate-100 p-3 transition-colors hover:border-slate-200 hover:bg-slate-50"
                      >
                        <span
                          style={{ backgroundColor: `${typeMeta.color}14`, color: typeMeta.color }}
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                        >
                          <typeMeta.icon className="h-4 w-4" aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-navy-800">{ev.title}</span>
                          <span className="block text-[11px] text-navy-400">
                            {ev.refNo} · {timeAgo(ev.collectedAt)}
                          </span>
                        </span>
                        <Badge variant={statusMeta.variant} dot>
                          {statusMeta.label}
                        </Badge>
                      </Link>
                    );
                  })}
          </CardBody>
        </Card>

        {/* Recent entities */}
        <Card>
          <CardHeader
            title="Recent Entities"
            subtitle="Identity resolution pending analyst review"
            actions={
              <Link to="network" className="flex items-center gap-1 text-[13px] font-medium text-teal-700 hover:text-teal-800">
                Entity explorer <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            }
          />
          <CardBody className="space-y-2.5">
            {!network
              ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-11" />)
              : recentEntities.length === 0
                ? <p className="py-6 text-center text-sm text-navy-400">No entities tracked yet.</p>
                : recentEntities.map((entity) => {
                    const typeMeta = ENTITY_TYPES[entity.type] || ENTITY_TYPES.asset;
                    const TypeIcon = typeMeta.icon;
                    const resolution = ENTITY_RESOLUTION[entity.resolution] || ENTITY_RESOLUTION.unverified;
                    return (
                      <Link
                        key={entity.id}
                        to={`network?entity=${entity.id}`}
                        className="flex items-center gap-3 rounded-lg border border-slate-100 p-2.5 transition-colors hover:border-slate-200 hover:bg-slate-50"
                      >
                        <span
                          style={{ backgroundColor: `${typeMeta.color}14`, color: typeMeta.color }}
                          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                        >
                          <TypeIcon className="h-3.5 w-3.5" aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-navy-800">{entity.name}</span>
                          <span className="block text-[11px] text-navy-400">
                            {typeMeta.label} · {entity.connections} connections
                          </span>
                        </span>
                        <Badge variant={resolution.variant} dot>
                          {resolution.label}
                        </Badge>
                      </Link>
                    );
                  })}
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent events */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent Events"
            actions={
              <Link to="timeline" className="flex items-center gap-1 text-[13px] font-medium text-teal-700 hover:text-teal-800">
                Full timeline <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            }
          />
          <CardBody>
            {!network ? (
              <div className="space-y-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : events.length === 0 ? (
              <p className="py-6 text-center text-sm text-navy-400">No events recorded yet.</p>
            ) : (
              <EventTimeline events={[...events].sort((a, b) => new Date(b.datetime) - new Date(a.datetime)).slice(0, 5)} entityById={entitiesById} />
            )}
          </CardBody>
        </Card>

        {/* Right stack */}
        <div className="space-y-6">
          <ActivityFeed items={activity?.items} isLoading={!activity} hideCase />

          <Card>
            <CardHeader title="Intelligence" subtitle="Mock analysis values — full view under the Intelligence tab" />
            <CardBody className="space-y-2">
              {intelligence ? (
                <>
                  {[
                    { label: 'Contradictions', value: intelligence.summary.conflictingEvidence, to: 'intelligence?tab=contradictions', tone: 'text-amber-700' },
                    { label: 'Hypotheses', value: intelligence.summary.activeHypotheses, to: 'intelligence?tab=hypotheses', tone: 'text-sky-700' },
                    { label: 'Investigation gaps', value: intelligence.summary.openGaps, to: 'intelligence?tab=gaps', tone: 'text-navy-700' },
                  ].map((row) => (
                    <button
                      key={row.label}
                      type="button"
                      onClick={() => navigate(row.to)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-left transition-colors hover:border-teal-300 hover:bg-teal-50/30"
                    >
                      <span className="text-[13px] font-medium text-navy-600">{row.label}</span>
                      <span className={`text-[15px] font-semibold ${row.tone}`}>{row.value}</span>
                    </button>
                  ))}
                </>
              ) : (
                Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-9" />)
              )}
            </CardBody>
          </Card>

          {/* Important relationships */}
          <Card>
            <CardHeader title="Important Relationships" subtitle="Highest analyst confidence in this case" />
            <CardBody className="space-y-2.5">
              {!network
                ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12" />)
                : importantRelationships.length === 0
                  ? <p className="py-6 text-center text-sm text-navy-400">No relationships mapped yet.</p>
                  : importantRelationships.map((rel) => {
                      const relMeta = RELATIONSHIP_TYPES[rel.type] || RELATIONSHIP_TYPES.associate;
                      const source = entitiesById[rel.sourceId];
                      const target = entitiesById[rel.targetId];
                      return (
                        <div key={rel.id} className="rounded-lg border border-slate-100 p-2.5">
                          <div className="flex items-center gap-2 text-[12.5px]">
                            <span className="truncate font-medium text-navy-700">{source?.name || '—'}</span>
                            <span className="shrink-0 text-navy-300">↔</span>
                            <span className="truncate font-medium text-navy-700">{target?.name || '—'}</span>
                          </div>
                          <div className="mt-1.5 flex items-center justify-between gap-2 pl-0.5">
                            <span className="flex items-center gap-1.5 text-[11px] text-navy-400">
                              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: relMeta.color }} aria-hidden />
                              {rel.label || relMeta.label} · {rel.strength}%
                            </span>
                            <Button variant="ghost" size="sm" icon={HelpCircle} onClick={() => setWhyRelationship(rel)}>
                              Why?
                            </Button>
                          </div>
                        </div>
                      );
                    })}
            </CardBody>
          </Card>
        </div>
      </div>

      {/* Why this connection? */}
      <RelationshipWhyModal
        open={Boolean(whyRelationship)}
        onClose={() => setWhyRelationship(null)}
        relationship={whyRelationship}
        entitiesById={entitiesById}
        evidence={evidence || []}
        investigationId={investigation.id}
      />
    </div>
  );
}
