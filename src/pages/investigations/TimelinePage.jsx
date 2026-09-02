import { useEffect, useMemo, useState } from 'react';
import { History, X } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { EventTimeline } from '@/components/timeline/EventTimeline';
import { EventDetailsModal } from '@/components/timeline/EventDetailsModal';
import { useInvestigation } from './InvestigationLayout';
import { intelligenceService, evidenceService } from '@/services';
import { EVENT_TYPES } from '@/lib/constants';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

export function TimelinePage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Timeline`);

  const [result, setResult] = useState(null);
  const [entities, setEntities] = useState([]);
  const [evidenceList, setEvidenceList] = useState([]);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Filters: date range, entity, event type, evidence source
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [entityFilter, setEntityFilter] = useState('all');
  const [type, setType] = useState('all');
  const [evidenceFilter, setEvidenceFilter] = useState('all');

  const [selectedEvent, setSelectedEvent] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([
      intelligenceService.getEvents(investigation.id),
      intelligenceService.getEntities(investigation.id),
      evidenceService.list(investigation.id),
    ])
      .then(([eventsRes, entitiesRes, evidenceRes]) => {
        if (!active) return;
        setResult(eventsRes);
        setEntities(entitiesRes);
        setEvidenceList(evidenceRes.items);
      })
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigation.id, reloadKey]);

  const entityById = useMemo(() => Object.fromEntries(entities.map((e) => [e.id, e])), [entities]);

  const filtered = useMemo(() => {
    if (!result) return [];
    const from = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : 0;
    const to = dateTo ? new Date(`${dateTo}T23:59:59`).getTime() : Infinity;
    return result.items.filter((event) => {
      const t = new Date(event.datetime).getTime();
      if (t < from || t > to) return false;
      if (entityFilter !== 'all' && !(event.entityIds || []).includes(entityFilter)) return false;
      if (type !== 'all' && event.type !== type) return false;
      if (evidenceFilter === 'none' && event.evidenceId) return false;
      if (evidenceFilter !== 'all' && evidenceFilter !== 'none' && event.evidenceId !== evidenceFilter) return false;
      return true;
    });
  }, [result, dateFrom, dateTo, entityFilter, type, evidenceFilter]);

  if (error) return <ErrorState title="Could not load the timeline" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!result) return <PageLoader label="Loading timeline…" />;

  const hasFilters = dateFrom || dateTo || entityFilter !== 'all' || type !== 'all' || evidenceFilter !== 'all';

  return (
    <Card>
      <CardBody className="space-y-5">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="w-40">
            <Input type="date" aria-label="From date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <span className="text-xs text-navy-300">to</span>
          <div className="w-40">
            <Input type="date" aria-label="To date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div className="w-44">
            <Select
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
              aria-label="Filter by entity"
              options={[{ value: 'all', label: 'All entities' }, ...entities.map((e) => ({ value: e.id, label: e.name }))]}
            />
          </div>
          <div className="w-40">
            <Select
              value={type}
              onChange={(e) => setType(e.target.value)}
              aria-label="Filter events by type"
              options={[{ value: 'all', label: 'All event types' }, ...Object.entries(EVENT_TYPES).map(([value, meta]) => ({ value, label: meta.label }))]}
            />
          </div>
          <div className="w-48">
            <Select
              value={evidenceFilter}
              onChange={(e) => setEvidenceFilter(e.target.value)}
              aria-label="Filter by evidence source"
              options={[
                { value: 'all', label: 'All evidence sources' },
                { value: 'none', label: 'No linked evidence' },
                ...evidenceList.map((e) => ({ value: e.id, label: `${e.refNo} — ${e.title.slice(0, 30)}` })),
              ]}
            />
          </div>
          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              icon={X}
              onClick={() => {
                setDateFrom('');
                setDateTo('');
                setEntityFilter('all');
                setType('all');
                setEvidenceFilter('all');
              }}
            >
              Clear
            </Button>
          )}
          <span className="ml-auto text-[12px] text-navy-300">
            {filtered.length} of {result.total} events · newest first
          </span>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            icon={History}
            title={hasFilters ? 'No events match these filters' : 'No events recorded yet'}
            description={
              hasFilters
                ? 'Widen the date range or clear a filter to see more of the timeline.'
                : 'Events are reconstructed from evidence and field reports by the analysis backend.'
            }
          />
        ) : (
          <EventTimeline events={filtered} entityById={entityById} onEventClick={setSelectedEvent} />
        )}
      </CardBody>

      <EventDetailsModal event={selectedEvent} entityById={entityById} onClose={() => setSelectedEvent(null)} />
    </Card>
  );
}
