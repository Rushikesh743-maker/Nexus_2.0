import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, Search, Layers, Sliders } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { CnaNetworkGraph } from '@/components/analysis/CnaNetworkGraph';
import { EvidenceTrail } from '@/components/analysis/EvidenceTrail';
import { SubjectDrawer } from '@/components/analysis/SubjectDrawer';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { CNA_EDGE_TYPES, CNA_NODE_TYPES, cnaEdgeLabel, cnaNodeType } from '@/lib/cna';
import { cn, formatDate } from '@/lib/utils';

const REPLAY_MS = 700;

/** Whole days between two ISO dates, used to size the replay slider. */
function daysBetween(a, b) {
  return Math.max(0, Math.round((new Date(b) - new Date(a)) / 86400000));
}

function addDays(iso, days) {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function AnalysisGraphPage() {
  const [minConfidence, setMinConfidence] = useState(0);
  const [nodeTypes, setNodeTypes] = useState(new Set(Object.keys(CNA_NODE_TYPES)));
  const [edgeTypes, setEdgeTypes] = useState(new Set());
  const [query, setQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState(null);
  const [drawerId, setDrawerId] = useState(null);
  const [trail, setTrail] = useState(null);

  // Timeline replay
  const [replayDay, setReplayDay] = useState(null);
  const [playing, setPlaying] = useState(false);
  const timer = useRef(null);

  const graph = useCnaResource(() => cnaService.getGraph({ minConfidence }), [minConfidence]);
  const communities = useCnaResource(() => cnaService.getCommunities(), []);
  const stats = useCnaResource(() => cnaService.getStats(), []);

  const nodes = graph.data?.nodes || [];
  const edges = graph.data?.edges || [];

  const timeline = stats.data?.timeline;
  const spanDays = timeline?.min && timeline?.max ? daysBetween(timeline.min, timeline.max) : 0;

  // Start the replay at the end of the window — the full network, as it stands.
  useEffect(() => {
    if (spanDays > 0 && replayDay === null) setReplayDay(spanDays);
  }, [spanDays, replayDay]);

  useEffect(() => {
    if (!playing || spanDays <= 0) return undefined;
    timer.current = setInterval(() => {
      setReplayDay((d) => {
        if (d === null) return 0;
        if (d >= spanDays) {
          setPlaying(false);
          return spanDays;
        }
        return d + 1;
      });
    }, REPLAY_MS / 4);
    return () => clearInterval(timer.current);
  }, [playing, spanDays]);

  const replayDate = timeline?.min && replayDay !== null ? addDays(timeline.min, replayDay) : null;
  const replayActive = replayDate !== null && replayDay < spanDays;

  /** Edges that had been observed on or before the replay date. */
  const visibleEdgeKeys = useMemo(() => {
    if (!replayActive || !replayDate) return null;
    const keys = new Set();
    edges.forEach((e) => {
      // An undated edge cannot be placed in time, so the replay leaves it out
      // rather than assuming a date for it.
      if (e.first_seen && e.first_seen.slice(0, 10) <= replayDate) keys.add(`${e.source}|${e.target}`);
    });
    return keys;
  }, [edges, replayActive, replayDate]);

  const visibleNodeIds = useMemo(() => {
    const byType = new Set(nodes.filter((n) => nodeTypes.has(n.type)).map((n) => n.id));

    // With no relationship filter and no replay, entity type alone decides.
    if (edgeTypes.size === 0 && (!replayActive || !visibleEdgeKeys)) return byType;

    // Otherwise keep only entities that still hold a visible link — honouring
    // the relationship filter and the replay date together, not either alone.
    const keep = new Set();
    edges.forEach((e) => {
      if (edgeTypes.size > 0 && !e.types?.some((t) => edgeTypes.has(t))) return;
      if (visibleEdgeKeys && !visibleEdgeKeys.has(`${e.source}|${e.target}`)) return;
      if (byType.has(e.source) && byType.has(e.target)) {
        keep.add(e.source);
        keep.add(e.target);
      }
    });
    return keep;
  }, [nodes, edges, nodeTypes, edgeTypes, replayActive, visibleEdgeKeys]);

  const edgeKeyFilter = useMemo(() => {
    if (edgeTypes.size === 0) return visibleEdgeKeys;
    const keys = new Set();
    edges.forEach((e) => {
      const key = `${e.source}|${e.target}`;
      if (!e.types?.some((t) => edgeTypes.has(t))) return;
      if (visibleEdgeKeys && !visibleEdgeKeys.has(key)) return;
      keys.add(key);
    });
    return keys;
  }, [edges, edgeTypes, visibleEdgeKeys]);

  const highlightIds = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    const hits = new Set(
      nodes
        .filter(
          (n) =>
            String(n.label || '').toLowerCase().includes(q) ||
            (n.aliases || []).some((a) => String(a).toLowerCase().includes(q)) ||
            (n.phones || []).some((p) => String(p).includes(q))
        )
        .map((n) => n.id)
    );
    return hits.size ? hits : new Set(['__none__']);
  }, [nodes, query]);

  const selected = useMemo(() => nodes.find((n) => n.id === selectedNode) || null, [nodes, selectedNode]);

  const presentEdgeTypes = useMemo(() => {
    const seen = new Set();
    edges.forEach((e) => (e.types || []).forEach((t) => seen.add(t)));
    return Array.from(seen);
  }, [edges]);

  function toggle(set, setter, key) {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setter(next);
  }

  function resetView() {
    setNodeTypes(new Set(Object.keys(CNA_NODE_TYPES)));
    setEdgeTypes(new Set());
    setQuery('');
    setMinConfidence(0);
    setReplayDay(spanDays);
    setPlaying(false);
    setSelectedNode(null);
  }

  if (graph.error && !graph.data) {
    return (
      <Card>
        <AnalysisError error={graph.error} onRetry={graph.reload} />
      </Card>
    );
  }

  const shownNodeCount = visibleNodeIds ? visibleNodeIds.size : nodes.length;
  const shownEdgeCount = edgeKeyFilter ? edgeKeyFilter.size : edges.length;

  return (
    <div className="space-y-5">
      {/* Controls */}
      <Card>
        <CardHeader
          title="Relationship graph"
          subtitle="Every edge carries its type, weight, confidence, time window and the source records that produced it."
          actions={
            <Button variant="outline" size="sm" icon={RotateCcw} onClick={resetView}>
              Reset
            </Button>
          }
        />
        <CardBody className="space-y-3.5">
          <div className="flex flex-wrap items-end gap-4">
            <div className="w-60">
              <Input
                icon={Search}
                placeholder="Search names, aliases, phones…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search the graph"
                hint="Devanagari spellings match too."
              />
            </div>

            <div className="min-w-[220px]">
              <label htmlFor="conf" className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium text-navy-700">
                <Sliders className="h-3.5 w-3.5" aria-hidden />
                Minimum confidence: <span className="font-mono">{minConfidence.toFixed(2)}</span>
              </label>
              <input
                id="conf"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value))}
                className="w-full accent-teal-600"
              />
            </div>
          </div>

          {/* Entity types */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-medium text-navy-500">Entities</span>
            {Object.entries(CNA_NODE_TYPES).map(([key, meta]) => {
              const on = nodeTypes.has(key);
              const count = nodes.filter((n) => n.type === key).length;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggle(nodeTypes, setNodeTypes, key)}
                  aria-pressed={on}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                    on ? 'text-white' : 'bg-slate-100 text-navy-400 hover:bg-slate-200'
                  )}
                  style={on ? { backgroundColor: meta.color } : undefined}
                >
                  <meta.icon className="h-3 w-3" aria-hidden />
                  {meta.label}
                  <span className="opacity-75">{count}</span>
                </button>
              );
            })}
          </div>

          {/* Relationship types */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-medium text-navy-500">Relationships</span>
            <button
              type="button"
              onClick={() => setEdgeTypes(new Set())}
              className={cn(
                'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                edgeTypes.size === 0 ? 'bg-navy-800 text-white' : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
              )}
            >
              All
            </button>
            {presentEdgeTypes.map((t) => {
              const on = edgeTypes.has(t);
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => toggle(edgeTypes, setEdgeTypes, t)}
                  aria-pressed={on}
                  className={cn(
                    'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                    on ? 'bg-navy-800 text-white' : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
                  )}
                  style={on ? undefined : { color: CNA_EDGE_TYPES[t]?.color }}
                >
                  {cnaEdgeLabel(t)}
                </button>
              );
            })}
          </div>

          {/* Timeline replay */}
          {spanDays > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3.5 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant={playing ? 'secondary' : 'subtle'}
                  size="sm"
                  icon={playing ? Pause : Play}
                  onClick={() => {
                    if (!playing && replayDay >= spanDays) setReplayDay(0);
                    setPlaying(!playing);
                  }}
                >
                  {playing ? 'Pause' : 'Replay'}
                </Button>
                <div className="min-w-[220px] flex-1">
                  <input
                    type="range"
                    min={0}
                    max={spanDays}
                    step={1}
                    value={replayDay ?? spanDays}
                    onChange={(e) => {
                      setPlaying(false);
                      setReplayDay(Number(e.target.value));
                    }}
                    className="w-full accent-teal-600"
                    aria-label="Network as it stood on this date"
                  />
                </div>
                <span className="font-mono text-[12px] font-semibold text-navy-800">
                  {replayDate ? formatDate(replayDate) : '—'}
                </span>
                {!replayActive && <Badge variant="teal">Full window</Badge>}
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-navy-400">
                Shows the network as it stood on the chosen date, from each edge's first observation.
                {timeline?.undated_edges > 0 &&
                  ` ${timeline.undated_edges} undated edge${timeline.undated_edges === 1 ? '' : 's'} cannot be placed in time and ${timeline.undated_edges === 1 ? 'is' : 'are'} excluded from the replay.`}
              </p>
            </div>
          )}

          <p className="text-[12px] text-navy-400">
            Showing <span className="font-semibold text-navy-700">{shownNodeCount}</span> of {nodes.length} entities and{' '}
            <span className="font-semibold text-navy-700">{shownEdgeCount}</span> of {edges.length} relationships.
          </p>
        </CardBody>
      </Card>

      {/* Graph */}
      {graph.loading && !graph.data ? (
        <Card>
          <CardBody>
            <AnalysisSkeleton rows={9} />
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-4">
          <div className="lg:col-span-3">
            <CnaNetworkGraph
              nodes={nodes}
              edges={edges}
              visibleNodeIds={visibleNodeIds}
              visibleEdgeKeys={edgeKeyFilter}
              highlightIds={highlightIds}
              selectedId={selectedNode}
              onSelectNode={setSelectedNode}
              onSelectEdge={(e) => e && setTrail({ a: e.source, b: e.target })}
            />
            <p className="mt-2 text-[11px] text-navy-400">
              Click an entity for its panel, or a relationship to see the source records behind it. Entity type is
              carried by shape as well as colour.
            </p>
          </div>

          {/* Side panel */}
          <div className="space-y-5">
            <Card>
              <CardHeader title={selected ? selected.label : 'Selected entity'} />
              <CardBody>
                {!selected ? (
                  <p className="text-[13px] text-navy-400">Select an entity in the graph.</p>
                ) : (
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="neutral">{cnaNodeType(selected.type).label}</Badge>
                      {selected.rank && <Badge variant="teal">Rank #{selected.rank}</Badge>}
                      {selected.community !== null && selected.community !== undefined && (
                        <Badge variant="info">Group {selected.community}</Badge>
                      )}
                    </div>

                    {selected.aliases?.length > 0 && (
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">Also recorded as</p>
                        <p className="mt-1 text-[13px] text-navy-600">{selected.aliases.join(' · ')}</p>
                      </div>
                    )}

                    {selected.phones?.length > 0 && (
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">Handsets</p>
                        <p className="mt-1 font-mono text-[12px] text-navy-600">{selected.phones.join(', ')}</p>
                      </div>
                    )}

                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">Prior record</p>
                      <p className="mt-1 text-[13px] text-navy-600">
                        {!selected.record_checked ? (
                          <span className="text-navy-400">
                            Not present in the criminal-history database — “not found”, which is not the same as
                            “cleared”.
                          </span>
                        ) : selected.prior_cases > 0 ? (
                          `${selected.prior_cases} prior case${selected.prior_cases === 1 ? '' : 's'} on record.`
                        ) : (
                          'Checked, with zero prior cases on record.'
                        )}
                      </p>
                    </div>

                    <Button variant="outline" size="sm" onClick={() => setDrawerId(selected.id)} className="w-full">
                      Full profile
                    </Button>
                  </div>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Sub-groups"
                subtitle={
                  communities.data
                    ? `${communities.data.count} detected · modularity ${communities.data.modularity}`
                    : undefined
                }
              />
              <CardBody className="space-y-2">
                {communities.loading && !communities.data ? (
                  <AnalysisSkeleton rows={3} />
                ) : communities.error ? (
                  <AnalysisError error={communities.error} onRetry={communities.reload} compact />
                ) : (
                  (communities.data?.groups || []).map((group, i) => (
                    <details key={i} className="rounded-lg border border-slate-200 px-3 py-2">
                      <summary className="flex cursor-pointer items-center justify-between text-[13px] font-medium text-navy-700">
                        <span className="flex items-center gap-1.5">
                          <Layers className="h-3.5 w-3.5 text-navy-300" aria-hidden />
                          Group {i}
                        </span>
                        <span className="text-[12px] text-navy-400">{group.length}</span>
                      </summary>
                      <ul className="mt-2 space-y-1">
                        {group.map((m) => (
                          <li key={m.id}>
                            <button
                              type="button"
                              onClick={() => setSelectedNode(m.id)}
                              className="text-left text-[12px] text-navy-500 hover:text-teal-700"
                            >
                              {m.label}
                              <span className="ml-1.5 text-navy-300">{cnaNodeType(m.type).label}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ))
                )}
                <p className="pt-1 text-[11px] leading-relaxed text-navy-400">
                  Louvain runs across sixteen seeds with the best-scoring partition kept, so the same data yields the
                  same groups on every run.
                </p>
              </CardBody>
            </Card>
          </div>
        </div>
      )}

      <AnalysisDisclosure />

      <SubjectDrawer nodeId={drawerId} open={Boolean(drawerId)} onClose={() => setDrawerId(null)} />
      <EvidenceTrail pair={trail} open={Boolean(trail)} onClose={() => setTrail(null)} />
    </div>
  );
}
