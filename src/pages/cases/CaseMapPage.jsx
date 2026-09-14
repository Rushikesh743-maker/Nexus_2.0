import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, WifiOff, X } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

function FitPoints({ points }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return undefined;
    if (points.length === 1) {
      map.setView(points[0], 13);
    } else {
      map.fitBounds(L.latLngBounds(points), { padding: [42, 42] });
    }
  }, [points, map]);
  return null;
}

function locationIcon() {
  return L.divIcon({
    className: 'nexus-pin',
    html: `<svg width="26" height="32" viewBox="0 0 24 30" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 1C6.9 1 3 4.9 3 10c0 6.3 9 18 9 18s9-11.7 9-18c0-5.1-3.9-9-9-9z" fill="#0d9488" stroke="var(--surface)" stroke-width="1.4"/>
      <circle cx="12" cy="10" r="3" fill="var(--surface)"/>
    </svg>`,
    iconSize: [26, 32],
    iconAnchor: [13, 30],
    popupAnchor: [0, -28],
  });
}

/**
 * Case map — every recorded location in the case, plotted from its
 * recorded coordinates (the platform never fabricates coordinates;
 * locations without coordinates are listed, not plotted).
 *
 * Deep-linkable: `?entity=<id>` restricts the map to the locations
 * reached by that entity's dated events (the graph's "show in map"
 * action), and `?location=<id>` highlights one location.
 */
export function CaseMapPage() {
  const { caseFile: c } = useCaseFile();
  const [params, setParams] = useSearchParams();
  const entityFilter = params.get('entity');
  const locationFilter = params.get('location');
  const { data: locations, error, loading, reload } = useCnaResource(
    () => caseService.listLocations(c.id),
    [c.id]
  );
  const { data: events } = useCnaResource(
    () => caseService.listTimeline(c.id),
    [c.id]
  );
  const { data: entities } = useCnaResource(
    () => caseService.listEntities(c.id),
    [c.id]
  );
  const [tileError, setTileError] = useState(false);

  const entityName = useMemo(
    () => (entityFilter
      ? entities?.find((e) => String(e.id) === entityFilter)?.canonical_name || null
      : null),
    [entityFilter, entities]
  );

  // locations reachable from this entity's dated events (entity -> events -> location)
  const entityLocationIds = useMemo(() => {
    if (!entityFilter) return null;
    const ids = new Set();
    for (const ev of events || []) {
      if (String(ev.entity_id) === entityFilter && ev.location_id != null) {
        ids.add(String(ev.location_id));
      }
    }
    return ids;
  }, [events, entityFilter]);

  const filtered = useMemo(() => {
    let list = locations || [];
    if (entityLocationIds) {
      list = list.filter((l) => entityLocationIds.has(String(l.id)));
    }
    return list;
  }, [locations, entityLocationIds]);

  const eventsFor = (locationId) =>
    (events || []).filter((ev) => String(ev.location_id) === String(locationId));

  const plotted = useMemo(
    () => filtered.filter((l) => l.latitude != null && l.longitude != null),
    [filtered]
  );
  const withoutCoordinates = useMemo(
    () => filtered.filter((l) => l.latitude == null || l.longitude == null),
    [filtered]
  );
  const points = useMemo(() => plotted.map((l) => [l.latitude, l.longitude]), [plotted]);

  if (loading && !locations) return <PageLoader label="Loading case map…" />;
  if (error && !locations) {
    return <ErrorState title="Could not load case locations" description={error.message} onRetry={reload} />;
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-soft px-4 py-2.5">
          <p className="text-[12.5px] font-medium text-navy-700">
            {filtered.length} location{filtered.length === 1 ? '' : 's'}
            {entityFilter && <span className="text-navy-400"> reached by {entityName || `entity ${entityFilter}`}</span>}
          </p>
          {entityFilter && (
            <button
              onClick={() => setParams((p) => { p.delete('entity'); p.delete('location'); return p; })}
              className="flex items-center gap-1 rounded-full border border-line bg-slate-50 px-2.5 py-1 text-[11.5px] font-medium text-navy-600 hover:bg-slate-100"
            >
              {entityName || `entity ${entityFilter}`}
              <X className="h-3 w-3" aria-hidden />
            </button>
          )}
        </div>
        {plotted.length ? (
          <div className="relative h-[520px]">
            <MapContainer center={points[0]} zoom={13} className="h-full w-full">
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                eventHandlers={{ tileerror: () => setTileError(true) }}
              />
              <FitPoints points={points} />
              {plotted.map((l) => {
                const related = eventsFor(l.id);
                const isFocus = locationFilter && String(l.id) === locationFilter;
                return (
                  <Marker
                    key={l.id}
                    position={[l.latitude, l.longitude]}
                    icon={locationIcon()}
                  >
                    <Popup>
                      <div className="space-y-1">
                        <p className="text-[13px] font-semibold">{l.name} {isFocus && <Badge variant="teal">focus</Badge>}</p>
                        <p className="text-[11.5px] opacity-70">
                          <span className="font-mono">{l.latitude.toFixed(4)}, {l.longitude.toFixed(4)}</span>
                        </p>
                        {related.length > 0 && (
                          <div className="space-y-0.5">
                            {related.slice(0, 3).map((ev) => (
                              <p key={ev.id} className="text-[11px] opacity-80">
                                {formatDateTime(ev.timestamp)} · {ev.event_type}
                              </p>
                            ))}
                            {related.length > 3 && <p className="text-[10.5px] opacity-60">+{related.length - 3} more events</p>}
                          </div>
                        )}
                        {l.metadata?.address && <p className="text-[11.5px] opacity-70">{l.metadata.address}</p>}
                        <p className="text-[11px] opacity-60">Synthetic demonstration data</p>
                      </div>
                    </Popup>
                  </Marker>
                );
              })}
            </MapContainer>
            {tileError && (
              <div className="absolute left-3 top-3 z-[1000] flex items-center gap-2 rounded-md border border-line bg-surface/95 px-3 py-2 text-[12px] text-navy-600 shadow-sm">
                <WifiOff className="h-3.5 w-3.5" aria-hidden />
                Street tiles unavailable offline — pins remain accurate.
              </div>
            )}
          </div>
        ) : (
          <EmptyState
            icon={MapPin}
            title={entityFilter && !filtered.length ? 'No locations reached by this entity' : 'No coordinates recorded'}
            description={
              entityFilter && !filtered.length
                ? 'This entity has no dated events tied to a recorded location yet.'
                : 'This case has locations but none carry coordinates yet, so there is nothing to plot. Coordinates are only ever recorded, never fabricated.'
            }
          />
        )}
      </Card>

      <Card>
        <CardHeader title="Locations" subtitle={`${filtered.length} in scope`} />
        <ul className="max-h-[480px] divide-y divide-line-soft overflow-y-auto">
          {filtered.map((l) => {
            const related = eventsFor(l.id);
            return (
              <li key={l.id} className="px-4 py-2.5">
                <p className="truncate text-[12.5px] font-medium text-navy-800" title={l.name}>{l.name}</p>
                <p className="mt-0.5 text-[11px] text-navy-400">
                  {l.latitude != null
                    ? <span className="figure">{l.latitude.toFixed(4)}, {l.longitude.toFixed(4)}</span>
                    : 'no coordinates recorded'}
                  {l.metadata?.area ? ` · ${l.metadata.area}` : ''}
                </p>
                {related.length > 0 && (
                  <p className="mt-0.5 text-[11px] text-navy-400">
                    {related.length} event{related.length > 1 ? 's' : ''} · last {formatDateTime(related[related.length - 1].timestamp)}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
        {withoutCoordinates.length > 0 && (
          <p className="border-t border-line-soft px-4 py-2 text-[11px] text-navy-400">
            {withoutCoordinates.length} location{withoutCoordinates.length > 1 ? 's' : ''} without coordinates not plotted.
          </p>
        )}
      </Card>
    </div>
  );
}
