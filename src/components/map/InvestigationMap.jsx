import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { WifiOff, MapPin } from 'lucide-react';
import { LOCATION_TYPES } from '@/lib/constants';
import { Badge } from '@/components/ui/Badge';
import { formatDate } from '@/lib/utils';

function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return undefined;
    if (points.length === 1) {
      map.setView(points[0], 14);
    } else {
      map.fitBounds(L.latLngBounds(points), { padding: [42, 42] });
    }
  }, [points, map]);
  return null;
}

function pinIcon(color) {
  return L.divIcon({
    className: 'nexus-pin',
    html: `<svg width="26" height="32" viewBox="0 0 24 30" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 1C6.9 1 3 4.9 3 10c0 6.3 9 18 9 18s9-11.7 9-18c0-5.1-3.9-9-9-9z" fill="${color}" stroke="#ffffff" stroke-width="1.4"/>
      <circle cx="12" cy="10" r="3" fill="#ffffff"/>
    </svg>`,
    iconSize: [26, 32],
    iconAnchor: [13, 30],
    popupAnchor: [0, -28],
  });
}

function stopIcon(index) {
  return L.divIcon({
    className: 'nexus-pin',
    html: `<span style="display:flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:9999px;background:#102a43;color:#fff;font-size:11px;font-weight:600;border:2px solid #fff;box-shadow:0 1px 3px rgb(16 42 67 / 0.3)">${index}</span>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
}

/**
 * Case map. Markers and movement traces are driven entirely by enriched
 * mock locations + recorded movement legs from the service layer — the UI
 * never invents coordinates. Street tiles need internet; an inline notice
 * appears when they cannot load (offline preview).
 */
export function InvestigationMap({ locations = [], movementLegs = [], className, resetKey = 0 }) {
  const [tileError, setTileError] = useState(false);
  const points = locations.map((l) => [l.lat, l.lng]);
  movementLegs.forEach((leg) => {
    points.push([leg.from.lat, leg.from.lng]);
    points.push([leg.to.lat, leg.to.lng]);
  });
  const center = points[0] || [18.7606, 73.8623];

  if (!locations.length) return null;

  return (
    <div className={`relative ${className || 'h-[540px] w-full'}`}>
      <MapContainer key={resetKey} center={center} zoom={11} scrollWheelZoom className="h-full w-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          eventHandlers={{ tileerror: () => setTileError(true) }}
        />

        {/* Recorded movement between mapped locations */}
        {movementLegs.map((leg) => (
          <Polyline
            key={leg.id}
            positions={[
              [leg.from.lat, leg.from.lng],
              [leg.to.lat, leg.to.lng],
            ]}
            pathOptions={{ color: '#334e68', weight: 2, dashArray: '6 8', opacity: 0.8 }}
          />
        ))}
        {movementLegs.map((leg, i) => (
          <Marker
            key={`stop-${leg.id}`}
            position={[(leg.from.lat + leg.to.lat) / 2, (leg.from.lng + leg.to.lng) / 2]}
            icon={stopIcon(i + 1)}
            title={`${leg.from.name} → ${leg.to.name}`}
          />
        ))}

        {locations.map((loc) => {
          const meta = LOCATION_TYPES[loc.type] || LOCATION_TYPES.business;
          return (
            <Marker key={loc.id} position={[loc.lat, loc.lng]} icon={pinIcon(meta.color)}>
              <Popup>
                <div className="min-w-[210px] space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <MapPin className="h-3.5 w-3.5 text-navy-400" aria-hidden />
                    <strong className="text-[13px] text-navy-800">{loc.name}</strong>
                  </div>
                  <Badge variant="neutral" dot>
                    {meta.label}
                  </Badge>
                  {loc.address && <p className="text-[12px] text-navy-500">{loc.address}</p>}
                  <dl className="mt-1 grid grid-cols-3 gap-2 border-t border-slate-100 pt-1.5 text-center">
                    <div>
                      <dt className="text-[9px] font-medium uppercase tracking-wide text-navy-300">Events</dt>
                      <dd className="text-[13px] font-semibold text-navy-800">{loc.eventsCount ?? 0}</dd>
                    </div>
                    <div>
                      <dt className="text-[9px] font-medium uppercase tracking-wide text-navy-300">Entities</dt>
                      <dd className="text-[13px] font-semibold text-navy-800">{(loc.entityIds || []).length}</dd>
                    </div>
                    <div>
                      <dt className="text-[9px] font-medium uppercase tracking-wide text-navy-300">Evidence</dt>
                      <dd className="text-[13px] font-semibold text-navy-800">{loc.evidenceCount ?? '—'}</dd>
                    </div>
                  </dl>
                  {loc.lastRecordedAt && (
                    <p className="text-[11px] text-navy-400">
                      Last recorded: <span className="font-medium text-navy-600">{formatDate(loc.lastRecordedAt)}</span>
                    </p>
                  )}
                  {loc.notes && <p className="text-[11.5px] leading-snug text-navy-400">{loc.notes}</p>}
                  <p className="font-mono text-[10px] text-navy-300">
                    {loc.lat.toFixed(4)}, {loc.lng.toFixed(4)}
                  </p>
                </div>
              </Popup>
            </Marker>
          );
        })}
        <FitBounds points={points} />
      </MapContainer>
      {tileError && (
        <div className="absolute left-1/2 top-3 z-[500] flex max-w-[92%] -translate-x-1/2 items-start gap-2 rounded-lg border border-amber-200 bg-white/95 px-3 py-2 text-xs text-amber-800 shadow-dropdown">
          <WifiOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            Street tiles could not load (offline preview). Markers, movement traces and coordinates are still plotted — tiles
            appear when the app has internet access.
          </span>
        </div>
      )}
    </div>
  );
}
