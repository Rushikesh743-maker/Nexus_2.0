import { useMemo, useState } from 'react';
import { MapPin, Search, RotateCcw } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/EmptyState';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { SubjectDrawer } from '@/components/analysis/SubjectDrawer';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { formatScore } from '@/lib/cna';
import { cn } from '@/lib/utils';

const PAD = 76;
const VIEW_W = 1000;
const VIEW_H = 620;

/**
 * Geospatial view.
 *
 * Deliberately a plain lat/lon projection on a grid rather than a tile map —
 * the same choice the reference console makes, and for the same reason: venue
 * wifi fails, and a demo that needs to reach a tile server is a demo that can
 * die on stage. Nothing here is fetched over the network beyond the case data
 * itself.
 *
 * It is honest about what it is: an equirectangular plot, not a street map.
 * Relative position is meaningful; road distance is not.
 */
export function AnalysisMapPage() {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [drawerId, setDrawerId] = useState(null);

  const graph = useCnaResource(() => cnaService.getGraph(), []);

  const nodes = graph.data?.nodes || [];
  const edges = graph.data?.edges || [];

  /** Locations the pipeline could place, plus how much activity each carries. */
  const places = useMemo(() => {
    const linkCount = new Map();
    edges.forEach((e) => {
      [e.source, e.target].forEach((id) => {
        linkCount.set(id, (linkCount.get(id) || 0) + 1);
      });
    });
    return nodes
      .filter((n) => typeof n.lat === 'number' && typeof n.lon === 'number')
      .map((n) => ({ ...n, links: linkCount.get(n.id) || 0 }))
      .sort((a, b) => b.links - a.links);
  }, [nodes, edges]);

  const bounds = useMemo(() => {
    if (!places.length) return null;
    const lats = places.map((p) => p.lat);
    const lons = places.map((p) => p.lon);
    return {
      la0: Math.min(...lats),
      la1: Math.max(...lats),
      lo0: Math.min(...lons),
      lo1: Math.max(...lons),
    };
  }, [places]);

  const maxLinks = Math.max(...places.map((p) => p.links), 1);

  const projected = useMemo(() => {
    if (!bounds) return [];
    const { la0, la1, lo0, lo1 } = bounds;
    const spanLo = lo1 - lo0 || 1;
    const spanLa = la1 - la0 || 1;
    return places.map((p) => ({
      ...p,
      x: PAD + ((p.lon - lo0) / spanLo) * (VIEW_W - PAD * 2),
      // SVG y grows downward, so north has to be flipped to the top.
      y: VIEW_H - PAD - ((p.lat - la0) / spanLa) * (VIEW_H - PAD * 2),
      // Halo radius tracks activity, matching the console's sizing.
      r: 7 + (p.links / maxLinks) * 22,
    }));
  }, [places, bounds, maxLinks]);

  const term = query.trim().toLowerCase();
  const matches = (p) => !term || String(p.label || '').toLowerCase().includes(term);

  if (graph.error && !graph.data) {
    return (
      <Card>
        <AnalysisError error={graph.error} onRetry={graph.reload} />
      </Card>
    );
  }

  const selectedPlace = projected.find((p) => p.id === selected) || null;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Locations"
          subtitle="Cell sites, FIR locations and surveillance points on one plane, sized by how much activity each carries. Coordinates come only from the source records — nothing is geocoded or inferred."
          actions={
            <div className="flex items-center gap-2">
              <div className="w-52">
                <Input
                  icon={Search}
                  placeholder="Find a location…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Find a location"
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                icon={RotateCcw}
                onClick={() => {
                  setQuery('');
                  setSelected(null);
                }}
              >
                Reset
              </Button>
            </div>
          }
        />
      </Card>

      {graph.loading && !graph.data ? (
        <Card>
          <CardBody>
            <AnalysisSkeleton rows={8} />
          </CardBody>
        </Card>
      ) : places.length === 0 ? (
        <Card>
          <EmptyState
            icon={MapPin}
            title="No located records in this case"
            description="No source record in the corpus carries coordinates, so there is nothing to place. Absence of a location is not evidence that an event had none."
          />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-4">
          {/* Plot */}
          <Card className="overflow-hidden lg:col-span-3">
            <div className="relative">
              <svg
                viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
                className="block h-[560px] w-full"
                style={{ background: 'var(--surface-sunken)' }}
                role="img"
                aria-label={`${places.length} located records plotted by coordinate`}
              >
                {/* Reference grid — the plot is a plane, and says so. */}
                <g stroke="var(--viz-grid)" strokeWidth="1">
                  {Array.from({ length: 9 }).map((_, i) => {
                    const x = PAD + (i / 8) * (VIEW_W - PAD * 2);
                    const y = PAD + (i / 8) * (VIEW_H - PAD * 2);
                    return (
                      <g key={i}>
                        <line x1={x} x2={x} y1={PAD} y2={VIEW_H - PAD} />
                        <line x1={PAD} x2={VIEW_W - PAD} y1={y} y2={y} />
                      </g>
                    );
                  })}
                </g>

                {projected.map((p) => {
                  const dim = term && !matches(p);
                  const active = selected === p.id;
                  return (
                    <g
                      key={p.id}
                      opacity={dim ? 0.18 : 1}
                      className="cursor-pointer"
                      onClick={() => setSelected(active ? null : p.id)}
                      tabIndex={0}
                      role="button"
                      aria-label={`${p.label}, ${p.links} links`}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelected(active ? null : p.id);
                        }
                      }}
                    >
                      {/* Halo: area carries activity volume. */}
                      <circle cx={p.x} cy={p.y} r={p.r} fill="var(--accent-surface)" />
                      {active && (
                        <circle
                          cx={p.x}
                          cy={p.y}
                          r={p.r + 4}
                          fill="none"
                          stroke="var(--accent)"
                          strokeWidth="1.5"
                        />
                      )}
                      <circle
                        cx={p.x}
                        cy={p.y}
                        r="4.5"
                        fill="var(--data-emerald)"
                        stroke="var(--surface)"
                        strokeWidth="2"
                      />
                      <text
                        x={p.x}
                        y={p.y + p.r + 15}
                        textAnchor="middle"
                        fontSize="12"
                        fill="var(--ink-900)"
                      >
                        {p.label}
                      </text>
                      <text
                        x={p.x}
                        y={p.y + p.r + 28}
                        textAnchor="middle"
                        fontSize="10"
                        fill="var(--ink-500)"
                      >
                        {p.links} link{p.links === 1 ? '' : 's'}
                      </text>
                    </g>
                  );
                })}
              </svg>

              <p className="absolute bottom-3 left-3 rounded border border-line bg-surface/90 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-navy-500">
                {places.length} locations · sized by activity
              </p>
            </div>
          </Card>

          {/* Side panel */}
          <div className="space-y-5">
            <Card>
              <CardHeader title={selectedPlace ? selectedPlace.label : 'Selected location'} />
              <CardBody>
                {!selectedPlace ? (
                  <p className="text-[12.5px] text-navy-400">
                    Select a point to see its coordinates and activity.
                  </p>
                ) : (
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="teal">{selectedPlace.links} links</Badge>
                      {selectedPlace.community !== null && selectedPlace.community !== undefined && (
                        <Badge variant="info">Group {selectedPlace.community}</Badge>
                      )}
                    </div>
                    <div>
                      <p className="label-micro">Coordinates</p>
                      <p className="figure mt-1 text-[12px] text-navy-700">
                        {formatScore(selectedPlace.lat, 4)}, {formatScore(selectedPlace.lon, 4)}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => setDrawerId(selectedPlace.id)}
                    >
                      Full record
                    </Button>
                  </div>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="By activity" subtitle="Links attested at each location." />
              <CardBody className="p-0">
                <Table className="min-w-0">
                  <THead>
                    <Tr>
                      <Th>Location</Th>
                      <Th className="w-16 text-right">Links</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {projected.filter(matches).map((p) => (
                      <Tr key={p.id} onClick={() => setSelected(p.id)} selected={selected === p.id}>
                        <Td className={cn('truncate', selected === p.id && 'text-accent')}>{p.label}</Td>
                        <Td className="figure text-right font-semibold">{p.links}</Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              </CardBody>
            </Card>
          </div>
        </div>
      )}

      <p className="text-[11.5px] leading-relaxed text-navy-400">
        This is an equirectangular plot, not a street map: relative position is meaningful, road
        distance is not. It renders without a tile server so the case remains reviewable offline.
      </p>

      <AnalysisDisclosure />

      <SubjectDrawer nodeId={drawerId} open={Boolean(drawerId)} onClose={() => setDrawerId(null)} />
    </div>
  );
}
