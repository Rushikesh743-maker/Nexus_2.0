import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Share2, HelpCircle, ArrowUpRight, History } from 'lucide-react';
import { Drawer } from '@/components/modals/Drawer';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Tabs } from '@/components/ui/Tabs';
import { Avatar } from '@/components/ui/Avatar';
import { EmptyState } from '@/components/ui/EmptyState';
import { ConfidenceMeter } from './ConfidenceMeter';
import { RelationshipWhyModal } from './RelationshipWhyModal';
import { evidenceService } from '@/services';
import { ENTITY_TYPES, ENTITY_RESOLUTION, RELATIONSHIP_TYPES, EVENT_TYPES, EVIDENCE_STATUS, FILE_TYPES } from '@/lib/constants';
import { formatDate, formatDateTime, cn } from '@/lib/utils';

/**
 * Entity details drawer — identity profile with Overview / Relationships /
 * Evidence / Events tabs. Data comes from the intelligence + evidence
 * services (mock today). Neutral presentation only.
 */
export function EntityDetailsDrawer({ open, entity, context, onClose }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');
  const [whyRelationship, setWhyRelationship] = useState(null);
  const [evidence, setEvidence] = useState(null);

  const investigationId = entity?.investigationId;
  const relationships = context?.relationships || [];
  const events = context?.events || [];

  // Case evidence for the Evidence tab + WHY panel.
  useEffect(() => {
    if (!open || !investigationId) return undefined;
    let active = true;
    setEvidence(null);
    evidenceService
      .list(investigationId)
      .then((r) => active && setEvidence(r.items))
      .catch(() => active && setEvidence([]));
    return () => {
      active = false;
    };
  }, [open, investigationId]);

  // Reset tab per entity.
  useEffect(() => {
    if (open) setTab('overview');
  }, [open, entity?.id]);

  const myRelationships = useMemo(
    () =>
      relationships
        .filter((r) => r.sourceId === entity?.id || r.targetId === entity?.id)
        .map((r) => ({
          rel: r,
          other: context?.entitiesById?.[r.sourceId === entity?.id ? r.targetId : r.sourceId],
        }))
        .filter((c) => c.other),
    [relationships, entity, context]
  );

  const myEvents = useMemo(() => events.filter((e) => (e.entityIds || []).includes(entity?.id)), [events, entity]);

  if (!entity) return null;

  const typeMeta = ENTITY_TYPES[entity.type] || ENTITY_TYPES.asset;
  const TypeIcon = typeMeta.icon;
  const resolution = ENTITY_RESOLUTION[entity.resolution] || ENTITY_RESOLUTION.unverified;

  const counts = {
    phones: myRelationships.filter((c) => c.other.type === 'phone_number').length,
    vehicles: myRelationships.filter((c) => c.other.type === 'vehicle').length,
    locations: myRelationships.filter((c) => c.other.type === 'address').length,
    cases: 1,
    evidence: entity.evidenceCount ?? '—',
  };

  return (
    <>
      <Drawer
        open={open}
        onClose={onClose}
        width={560}
        title={entity.name}
        subtitle={`${entity.code || ''} · ${typeMeta.label}`}
        footer={
          <Button
            variant="outline"
            icon={Share2}
            onClick={() => {
              onClose();
              navigate(`/investigations/${investigationId}/network?entity=${entity.id}`);
            }}
          >
            Show in Network
          </Button>
        }
      >
        <div className="space-y-5">
          {/* Identity header */}
          <div className="flex items-start gap-3">
            <Avatar name={entity.name} size="lg" />
            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="neutral">
                  <TypeIcon className="mr-1 h-3 w-3" aria-hidden />
                  {typeMeta.label}
                </Badge>
                {entity.role && <Badge variant="teal">{entity.role}</Badge>}
                <Badge variant={resolution.variant} dot>
                  {resolution.label}
                </Badge>
              </div>
              {entity.resolutionConfidence != null && (
                <ConfidenceMeter value={entity.resolutionConfidence} label="Match confidence" />
              )}
            </div>
          </div>

          <p className="text-[11px] leading-relaxed text-navy-300">
            Resolution reflects automated identity matching (mock data) — an analyst confirms every match before it is relied
            upon. NEXUS records subjects and matches; it does not label people.
          </p>

          <Tabs
            value={tab}
            onChange={setTab}
            tabs={[
              { id: 'overview', label: 'Overview' },
              { id: 'relationships', label: `Relationships (${myRelationships.length})` },
              { id: 'evidence', label: 'Evidence' },
              { id: 'events', label: `Events (${myEvents.length})` },
            ]}
          />

          {tab === 'overview' && (
            <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <CountTile label="Aliases" value={(entity.aliases || []).length} />
                <CountTile label="Associated Phones" value={counts.phones} />
                <CountTile label="Vehicles" value={counts.vehicles} />
                <CountTile label="Locations" value={counts.locations} />
                <CountTile label="Cases" value={counts.cases} />
                <CountTile label="Evidence" value={counts.evidence} />
              </dl>

              {(entity.aliases || []).length > 0 && (
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">Aliases</h4>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {entity.aliases.map((alias) => (
                      <Badge key={alias} variant="neutral">
                        {alias}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {entity.notes && (
                <div>
                  <h4 className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">Notes</h4>
                  <p className="mt-1 text-[13px] leading-relaxed text-navy-500">{entity.notes}</p>
                </div>
              )}

              {Object.entries(entity.attributes || {}).length > 0 && (
                <dl className="space-y-1.5 rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                  {Object.entries(entity.attributes).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3 text-[12px]">
                      <dt className="capitalize text-navy-400">{k.replace(/Masked$/, '')}</dt>
                      <dd className="text-right font-medium text-navy-600">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          )}

          {tab === 'relationships' && (
            <ul className="space-y-2.5">
              {myRelationships.length === 0 && <EmptyState compact title="No recorded relationships" />}
              {myRelationships.map(({ rel, other }) => {
                const relMeta = RELATIONSHIP_TYPES[rel.type] || RELATIONSHIP_TYPES.associate;
                return (
                  <li key={rel.id} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex items-center gap-2.5">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: relMeta.color }} aria-hidden />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-navy-700">{other.name}</span>
                      <Badge variant="neutral">{relMeta.label}</Badge>
                    </div>
                    <p className="mt-1 pl-[18px] text-[12px] text-navy-400">{rel.label || relMeta.label}</p>
                    <div className="mt-2 flex items-center gap-3 pl-[18px]">
                      <div className="w-28">
                        <ConfidenceMeter value={rel.strength} label="Confidence" />
                      </div>
                      <Button variant="ghost" size="sm" icon={HelpCircle} onClick={() => setWhyRelationship(rel)}>
                        Why this connection?
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {tab === 'evidence' && (
            <div className="space-y-2">
              {!evidence ? (
                <p className="py-4 text-center text-[13px] text-navy-300">Loading case evidence…</p>
              ) : evidence.length === 0 ? (
                <EmptyState compact title="No evidence in this case yet" />
              ) : (
                evidence.slice(0, 8).map((ev) => {
                  const statusMeta = EVIDENCE_STATUS[ev.status] || EVIDENCE_STATUS.uploaded;
                  return (
                    <button
                      key={ev.id}
                      type="button"
                      onClick={() => {
                        onClose();
                        navigate(`/investigations/${investigationId}/evidence?evidence=${ev.id}`);
                      }}
                      className="flex w-full items-center gap-3 rounded-lg border border-slate-200 px-3 py-2.5 text-left transition-colors hover:border-teal-300 hover:bg-teal-50/30"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-navy-700">{ev.title}</span>
                        <span className="text-[11px] text-navy-300">
                          {ev.refNo} · {FILE_TYPES[ev.fileType]?.label || 'file'} · {formatDate(ev.collectedAt)}
                        </span>
                      </span>
                      <Badge variant={statusMeta.variant} dot>
                        {statusMeta.label}
                      </Badge>
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                    </button>
                  );
                })
              )}
              <p className="pt-1 text-[11px] text-navy-300">
                Links between this entity and evidence records are placeholders until the extraction pipeline maps them.
              </p>
            </div>
          )}

          {tab === 'events' && (
            <div className="space-y-0">
              {myEvents.length === 0 ? (
                <EmptyState compact icon={History} title="No events involve this entity" />
              ) : (
                myEvents.map((event, i, arr) => {
                  const evMeta = EVENT_TYPES[event.type] || EVENT_TYPES.report;
                  const EvIcon = evMeta.icon;
                  return (
                    <div
                      key={event.id}
                      className={cn('relative flex gap-3 pb-4', i < arr.length - 1 && 'border-l border-slate-100 ml-4')}
                    >
                      <span
                        style={{ backgroundColor: `${evMeta.color}14`, color: evMeta.color }}
                        className="relative -ml-[18px] flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white ring-4 ring-white"
                      >
                        <EvIcon className="h-4 w-4" aria-hidden />
                      </span>
                      <div className="min-w-0 flex-1 pt-1">
                        <p className="text-[13px] font-medium text-navy-700">{event.title}</p>
                        <p className="mt-0.5 text-[11px] text-navy-300">{formatDateTime(event.datetime)}</p>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </Drawer>

      <RelationshipWhyModal
        open={Boolean(whyRelationship)}
        onClose={() => setWhyRelationship(null)}
        relationship={whyRelationship}
        entitiesById={context?.entitiesById || {}}
        evidence={evidence || []}
        investigationId={investigationId}
      />
    </>
  );
}

function CountTile({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 p-2.5 text-center">
      <p className="text-lg font-semibold leading-none text-navy-900">{value ?? '—'}</p>
      <p className="mt-1 text-[10px] font-medium uppercase tracking-wide text-navy-300">{label}</p>
    </div>
  );
}
