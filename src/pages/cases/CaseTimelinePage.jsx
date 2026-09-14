import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Clock, X } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { DataTable } from '@/components/tables/DataTable';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

/**
 * Case timeline — dated occurrences in chronological order.
 *
 * Deep-linkable: `?entity=<entityId>` filters the events to one entity
 * (set by the graph's "show in timeline" action) — the same case data,
 * a real filter, no invented rows.
 */
export function CaseTimelinePage() {
  const { caseFile: c } = useCaseFile();
  const [params, setParams] = useSearchParams();
  const entityFilter = params.get('entity');

  const { data: events, error, loading, reload } = useCnaResource(
    () => caseService.listTimeline(c.id),
    [c.id]
  );

  const { data: entities } = useCnaResource(
    () => caseService.listEntities(c.id),
    [c.id]
  );
  const entityName = useMemo(
    () => (entityFilter
      ? entities?.find((e) => String(e.id) === entityFilter)?.canonical_name || null
      : null),
    [entityFilter, entities]
  );

  const filtered = useMemo(
    () => (entityFilter
      ? (events || []).filter((e) => String(e.entity_id) === entityFilter)
      : events || []),
    [events, entityFilter]
  );

  const columns = [
    {
      key: 'timestamp',
      header: 'When',
      render: (e) => <span className="figure text-[11.5px] text-navy-600">{formatDateTime(e.timestamp)}</span>,
    },
    { key: 'event_type', header: 'Type', render: (e) => <Badge variant="teal">{e.event_type}</Badge> },
    {
      key: 'description',
      header: 'Event',
      render: (e) => <span className="block text-[13px] text-navy-800">{e.description}</span>,
    },
  ];

  return (
    <Card>
      <CardHeader
        title="Timeline"
        subtitle={
          events?.length
            ? `${filtered.length}${entityFilter ? ` of ${events.length}` : ''} dated events, oldest first`
            : 'Dated occurrences recorded into this case'
        }
        actions={
          entityFilter && (
            <button
              onClick={() => setParams((p) => { p.delete('entity'); return p; })}
              className="flex items-center gap-1 rounded-full border border-line bg-slate-50 px-2.5 py-1 text-[11.5px] font-medium text-navy-600 hover:bg-slate-100"
            >
              {entityName || `entity ${entityFilter}`}
              <X className="h-3 w-3" aria-hidden />
            </button>
          )
        }
      />
      <DataTable
        columns={columns}
        data={filtered}
        getRowId={(e) => e.id}
        isLoading={loading}
        error={error}
        onRetry={reload}
        emptyIcon={Clock}
        emptyTitle={entityFilter ? 'No events for this entity' : 'No timeline events'}
        emptyDescription={
          entityFilter
            ? 'This entity has no dated events recorded in the case timeline yet.'
            : 'Dated occurrences — sightings, registrations, calls — recorded into this case will appear here.'
        }
      />
    </Card>
  );
}
