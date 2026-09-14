import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  User,
  Phone,
  Car,
  Building2,
  MapPin,
  Wallet,
  Briefcase,
  Tag,
  CalendarClock,
  FileText,
  Link2,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { buttonClasses } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { FreshnessBadge } from '@/components/cases/FreshnessBadge';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

const TYPE_META = {
  person: { label: 'Person', icon: User },
  phone: { label: 'Phone', icon: Phone },
  vehicle: { label: 'Vehicle', icon: Car },
  organization: { label: 'Organization', icon: Building2 },
  location: { label: 'Location', icon: MapPin },
  account: { label: 'Account', icon: Wallet },
  case_reference: { label: 'Case reference', icon: Briefcase },
  event: { label: 'Event', icon: CalendarClock },
  other: { label: 'Other', icon: Tag },
};

/**
 * Entity focus panel (phase 2, work item G).
 *
 * Everything this ONE case knows about a single confirmed entity, from the
 * backend profile endpoint — connections with provenance back to the source
 * document/snippet, evidence with its structured claims (original text),
 * timeline events, locations (coordinates only from confirmed rows),
 * findings that involve it, and computed metrics. Plus cross-mode focus
 * links so the same entity can be opened in Timeline / Map / Evidence /
 * Graph — the `?entity=` deep link carries the focus across mode switches.
 * Confirmed data only; the case's analysis freshness is shown, not assumed.
 */
export function CaseEntityProfilePage() {
  const { caseId, entityId } = useParams();
  const { caseFile: c } = useCaseFile();
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => caseService.getEntityProfile(Number(caseId), Number(entityId)),
      [caseId, entityId]),
    [caseId, entityId]
  );

  if (loading && !data) return <PageLoader label="Loading entity profile…" />;
  if (error && !data) {
    return <ErrorState title="Entity profile unavailable" description={error.message} onRetry={reload} />;
  }
  if (!data) return null;

  const e = data.entity;
  const meta = TYPE_META[e.entity_type] || TYPE_META.other;
  const Icon = meta.icon;
  const aliases = e.metadata?.aliases || [];

  // cross-mode focus links — the focused entity rides along as ?entity=
  const focus = (to) => `/cases/${c.id}${to}?entity=${e.id}`;
  const hasEvidence = (data.evidence || []).length > 0;

  return (
    <div className="space-y-4">
      <div>
        <Link
          to={`/cases/${c.id}/entities`}
          className="mb-2 inline-flex items-center gap-1 text-[12px] font-medium text-navy-500 hover:text-navy-900"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> All entities
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-surface-sunken text-navy-600">
            <Icon className="h-5 w-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="font-display text-[22px] leading-tight text-navy-900">{e.canonical_name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Badge variant="teal">{meta.label}</Badge>
              {aliases.length > 0 && (
                <span className="text-[11.5px] text-navy-400">
                  also known as {aliases.slice(0, 4).join(', ')}{aliases.length > 4 && ` +${aliases.length - 4}`}
                </span>
              )}
              <FreshnessBadge analysis={data.analysis} />
            </div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-wide text-navy-400">View in</span>
          {[
            { to: '/timeline', label: 'Timeline', Icon: CalendarClock },
            { to: '/map', label: 'Map', Icon: MapPin },
            { to: '/evidence', label: 'Evidence', Icon: FileText },
            { to: '/graph', label: 'Graph', Icon: Link2 },
          ].map(({ to, label, Icon }) => (
            <Link
              key={to}
              to={focus(to)}
              className={buttonClasses('outline', 'sm')}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden />
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {/* metrics */}
        <Card>
          <CardHeader title="Metrics" actions={<Badge variant="default">computed</Badge>} />
          <dl className="divide-y divide-line-soft">
            {[
              ['Connections', data.metrics?.degree ?? 0],
              ['Source documents', data.metrics?.documents ?? 0],
              ['First seen', data.metrics?.first_seen ? formatDateTime(data.metrics.first_seen) : '—'],
              ['Last seen', data.metrics?.last_seen ? formatDateTime(data.metrics.last_seen) : '—'],
              ['Time span', data.metrics?.time_span_hours != null ? `${data.metrics.time_span_hours} h` : '—'],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center justify-between px-4 py-2.5">
                <dt className="text-[12px] text-navy-400">{k}</dt>
                <dd className="figure text-[13px] text-navy-800">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        {/* connections */}
        <Card className="xl:col-span-2">
          <CardHeader
            title="Connections"
            actions={<Badge variant={data.connections?.length ? 'default' : 'neutral'}>{data.connections?.length ?? 0}</Badge>}
          />
          {(data.connections || []).length === 0 ? (
            <p className="px-4 py-3 text-[12px] text-navy-400">No confirmed relationships touch this entity yet.</p>
          ) : (
            <ul className="divide-y divide-line-soft">
              {data.connections.map((conn) => (
                <li key={conn.relationship_id} className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[12px] text-navy-400">{conn.direction === 'outgoing' ? '→' : '←'}</span>
                    <Badge variant="neutral">{conn.relationship_type}</Badge>
                    {conn.peer ? (
                      <Link
                        to={`/cases/${c.id}/entities/${conn.peer.id}`}
                        className="text-[13px] font-medium text-navy-800 hover:text-navy-900 hover:underline"
                      >
                        {conn.peer.canonical_name}
                      </Link>
                    ) : (
                      <span className="text-[13px] text-navy-500">unknown peer</span>
                    )}
                    {typeof conn.confidence === 'number' && (
                      <span className="figure ml-auto text-[10.5px] text-navy-400">
                        {Math.round(conn.confidence * 100)}% confidence
                      </span>
                    )}
                  </div>
                  {conn.provenance?.snippet && (
                    <p className="mt-1 text-[11.5px] italic text-navy-400">“{conn.provenance.snippet}”</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {/* evidence + claims */}
        <Card>
          <CardHeader
            title="Evidence & structured claims"
            actions={<Badge variant={hasEvidence ? 'default' : 'neutral'}>{data.evidence?.length ?? 0} evidence</Badge>}
          />
          {(data.evidence || []).length === 0 ? (
            <p className="px-4 py-3 text-[12px] text-navy-400">No confirmed evidence is linked to this entity.</p>
          ) : (
            <ul className="divide-y divide-line-soft">
              {data.evidence.map((ev) => (
                <li key={ev.id} className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/cases/${c.id}/evidence?evidence=${ev.id}`}
                      className="figure text-[10.5px] text-accent hover:underline"
                    >
                      E{ev.id}
                    </Link>
                    <Badge variant="neutral">{ev.evidence_type}</Badge>
                    {ev.document && <span className="figure text-[11px] text-navy-400">{ev.document}</span>}
                  </div>
                  {ev.description && <p className="mt-1 text-[12px] text-navy-600">{ev.description}</p>}
                  {(ev.claims || []).length > 0 && (
                    <ul className="mt-1.5 space-y-1">
                      {ev.claims.map((cl) => (
                        <li key={cl.id} className="rounded bg-surface-sunken/50 px-2.5 py-1.5 text-[11.5px] text-navy-600">
                          <span className="font-medium text-navy-800">{cl.predicate}</span>
                          {cl.object_entity && <> → {cl.object_entity.canonical_name}</>}
                          {cl.object_value && !cl.object_entity && <> → <span className="italic">{cl.object_value}</span></>}
                          {cl.event_time && <span className="figure ml-1.5 text-navy-400">{formatDateTime(cl.event_time)}</span>}
                          {cl.original_text && (
                            <span className="mt-0.5 block text-[11px] italic text-navy-400">“{cl.original_text}”</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* events + locations + findings */}
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Timeline events"
              actions={<Badge variant={(data.events?.length ?? 0) ? 'default' : 'neutral'}>{data.events?.length ?? 0}</Badge>}
            />
            {(data.events || []).length === 0 ? (
              <p className="px-4 py-3 text-[12px] text-navy-400">No timeline events for this entity.</p>
            ) : (
              <ul className="divide-y divide-line-soft">
                {data.events.map((ev) => (
                  <li key={ev.id} className="px-4 py-2.5 text-[12px]">
                    <div className="flex items-center gap-2">
                      <span className="figure text-navy-400">{ev.timestamp ? formatDateTime(ev.timestamp) : 'undated'}</span>
                      <Badge variant="neutral">{ev.event_type}</Badge>
                      {ev.location && <span className="text-navy-500">@ {ev.location}</span>}
                    </div>
                    {ev.description && <p className="mt-0.5 text-navy-600">{ev.description}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Locations"
              actions={<Badge variant={(data.locations?.length ?? 0) ? 'default' : 'neutral'}>{data.locations?.length ?? 0}</Badge>}
            />
            {(data.locations || []).length === 0 ? (
              <p className="px-4 py-3 text-[12px] text-navy-400">No locations recorded for this entity.</p>
            ) : (
              <ul className="divide-y divide-line-soft">
                {data.locations.map((l, i) => (
                  <li key={i} className="flex items-center justify-between px-4 py-2.5 text-[12px]">
                    <span className="font-medium text-navy-700">{l.name}</span>
                    <span className="figure text-navy-400">
                      {l.latitude != null && l.longitude != null
                        ? `${l.latitude.toFixed(4)}, ${l.longitude.toFixed(4)}`
                        : 'no confirmed coordinates'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Findings involving this entity"
              actions={<Badge variant={(data.findings?.length ?? 0) ? 'default' : 'neutral'}>{data.findings?.length ?? 0}</Badge>}
            />
            {(data.findings || []).length === 0 ? (
              <p className="px-4 py-3 text-[12px] text-navy-400">No findings involve this entity.</p>
            ) : (
              <ul className="divide-y divide-line-soft">
                {data.findings.map((f) => (
                  <li key={f.id} className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
                      <Badge variant="neutral">{f.finding_type}</Badge>
                      <span className="min-w-0 truncate text-[12.5px] font-medium text-navy-800" title={f.title}>{f.title}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

export default CaseEntityProfilePage;
