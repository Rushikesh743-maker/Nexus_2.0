import { useEffect, useMemo, useState } from 'react';
import { MapPin, Route, RotateCcw, Search } from 'lucide-react';
import { Card, CardFooter } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { InvestigationMap } from '@/components/map/InvestigationMap';
import { useInvestigation } from './InvestigationLayout';
import { intelligenceService } from '@/services';
import { LOCATION_TYPES, EVENT_TYPES } from '@/lib/constants';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { cn } from '@/lib/utils';

const EVENT_TYPE_OPTIONS = [
  { value: 'all', label: 'All event types' },
  ...Object.entries(EVENT_TYPES).map(([value, meta]) => ({ value, label: meta.label })),
];

const DATE_OPTIONS = [
  { value: 'all', label: 'All time' },
  { value: '30', label: 'Last 30 days of activity' },
  { value: '90', label: 'Last 90 days of activity' },
];

export function MapPage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Map`);

  const [locations, setLocations] = useState(null);
  const [movement, setMovement] = useState(null);
  const [entities, setEntities] = useState([]);
  const [eventsForFilter, setEventsForFilter] = useState([]);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [mapKey, setMapKey] = useState(0);

  // Controls
  const [search, setSearch] = useState('');
  const [entityFilter, setEntityFilter] = useState('all');
  const [eventTypeFilter, setEventTypeFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('all');
  const [showMovement, setShowMovement] = useState(true);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([
      intelligenceService.getLocations(investigation.id),
      intelligenceService.getMovement(investigation.id),
      intelligenceService.getEvents(investigation.id),
      intelligenceService.getEntities(investigation.id),
    ])
      .then(([locs, mov, evs, ents]) => {
        if (!active) return;
        setLocations(locs);
        setMovement(mov);
        setEventsForFilter(evs.items);
        setEntities(ents);
      })
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigation.id, reloadKey]);

  const filteredLocations = useMemo(() => {
    if (!locations) return [];
    const term = search.trim().toLowerCase();
    const cutoff = dateFilter === 'all' ? 0 : Date.now() - parseInt(dateFilter, 10) * 24 * 60 * 60 * 1000;
    return locations.filter((loc) => {
      if (term && ![loc.name, loc.address || '', loc.notes || ''].join(' ').toLowerCase().includes(term)) return false;
      if (entityFilter !== 'all' && !(loc.entityIds || []).includes(entityFilter)) return false;
      if (eventTypeFilter !== 'all') {
        const hasType = eventsForFilter.some((e) => e.locationId === loc.id && e.type === eventTypeFilter);
        if (!hasType) return false;
      }
      if (cutoff) {
        const linked = eventsForFilter.filter((e) => e.locationId === loc.id);
        const times = linked.length ? linked.map((e) => new Date(e.datetime).getTime()) : [new Date(loc.lastActivityAt || 0).getTime()];
        if (!times.some((t) => t >= cutoff)) return false;
      }
      return true;
    });
  }, [locations, search, entityFilter, eventTypeFilter, dateFilter, eventsForFilter]);

  const filteredLegs = useMemo(() => {
    if (!movement || !showMovement) return [];
    const visible = new Set(filteredLocations.map((l) => l.id));
    return movement.legs.filter((leg) => visible.has(leg.from.id) && visible.has(leg.to.id));
  }, [movement, showMovement, filteredLocations]);

  const resetControls = () => {
    setSearch('');
    setEntityFilter('all');
    setEventTypeFilter('all');
    setDateFilter('all');
    setShowMovement(true);
    setMapKey((k) => k + 1);
  };

  if (error) return <ErrorState title="Could not load locations" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!locations || !movement) return <PageLoader label="Loading case map…" />;

  if (locations.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={MapPin}
          title="No mapped locations for this case"
          description="Geocoded places of interest appear here once the backend geocoding pipeline is connected."
        />
      </Card>
    );
  }

  const presentTypes = [...new Set(filteredLocations.map((l) => l.type))];
  const entityOptions = [
    { value: 'all', label: 'All entities' },
    ...entities.map((e) => ({ value: e.id, label: e.name })),
  ];

  return (
    <Card className="overflow-hidden">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
        <div className="w-48">
          <Input icon={Search} placeholder="Search location…" aria-label="Search location" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="w-44">
          <Select value={entityFilter} onChange={(e) => setEntityFilter(e.target.value)} options={entityOptions} aria-label="Filter by entity" />
        </div>
        <div className="w-40">
          <Select value={eventTypeFilter} onChange={(e) => setEventTypeFilter(e.target.value)} options={EVENT_TYPE_OPTIONS} aria-label="Filter by event type" />
        </div>
        <div className="w-48">
          <Select value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} options={DATE_OPTIONS} aria-label="Filter by date" />
        </div>
        <button
          type="button"
          onClick={() => setShowMovement((s) => !s)}
          aria-pressed={showMovement}
          className={cn(
            'flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-[12px] font-medium transition-colors',
            showMovement ? 'border-teal-500 bg-teal-50 text-teal-800' : 'border-slate-200 bg-white text-navy-500 hover:border-teal-300'
          )}
        >
          <Route className="h-3.5 w-3.5" aria-hidden />
          Show movement
        </button>
        <Button variant="ghost" size="sm" icon={RotateCcw} onClick={resetControls} className="ml-auto">
          Reset
        </Button>
      </div>

      {filteredLocations.length === 0 ? (
        <div className="flex h-[560px] items-center justify-center">
          <EmptyState
            icon={MapPin}
            title="No locations match these filters"
            description="Adjust the search, entity or date filters — or press Reset."
          />
        </div>
      ) : (
        <InvestigationMap
          locations={filteredLocations}
          movementLegs={filteredLegs}
          className="h-[560px] w-full"
          resetKey={mapKey}
        />
      )}

      <CardFooter className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">Legend</span>
        {presentTypes.map((type) => {
          const meta = LOCATION_TYPES[type] || LOCATION_TYPES.business;
          return (
            <span key={type} className="flex items-center gap-1.5 text-[12px] text-navy-500">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
              {meta.label}
            </span>
          );
        })}
        {showMovement && filteredLegs.length > 0 && (
          <span className="flex items-center gap-1.5 text-[12px] text-navy-500">
            <span className="inline-block h-0 w-6 border-t-2 border-dashed border-navy-700" aria-hidden />
            Movement trace ({filteredLegs.length} legs)
          </span>
        )}
        <span className="ml-auto text-[11px] text-navy-300">
          {filteredLocations.length} of {locations.length} locations · click a pin for details
        </span>
      </CardFooter>
    </Card>
  );
}
