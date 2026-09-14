import { memo, useMemo, useEffect, useRef } from 'react';
import ReactFlow, { Background, Controls, Handle, Position } from 'reactflow';
import 'reactflow/dist/style.css';
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from 'd3-force';
import { cnaEdgeColor, cnaEdgeLabel, cnaNodeType } from '@/lib/cna';
import { cn, truncate } from '@/lib/utils';

/**
 * Node glyph.
 *
 * Type is carried by shape *as well as* colour: five entity types exceed the
 * number of hues that stay separable under colour-vision deficiency when any
 * pair can sit side by side, so identity never rests on colour alone.
 */
const SHAPE_CLASS = {
  circle: 'rounded-full',
  square: 'rounded-md',
  diamond: 'rounded-md rotate-45',
  hexagon: 'rounded-[30%]',
  triangle: 'rounded-[35%]',
};

const CnaNode = memo(({ data }) => {
  const { node, dimmed, highlighted, selected } = data;
  const meta = cnaNodeType(node.type);

  return (
    <div
      className={cn(
        'w-[172px] rounded-xl border bg-white p-2.5 transition-opacity',
        selected || highlighted
          ? 'border-teal-500 shadow-md ring-2 ring-teal-500/50'
          : 'border-slate-200 shadow-card hover:shadow-md',
        dimmed ? 'opacity-20' : 'opacity-100'
      )}
      style={{ borderTop: `3px solid ${meta.color}` }}
    >
      <Handle type="target" position={Position.Top} className="!invisible" />
      <div className="flex items-center gap-2.5">
        <span
          style={{
            backgroundColor: `color-mix(in srgb, ${meta.color} 15%, transparent)`,
            color: meta.color,
          }}
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center text-[10px] font-bold',
            SHAPE_CLASS[meta.shape] || SHAPE_CLASS.circle
          )}
          title={meta.label}
        >
          <span className={meta.shape === 'diamond' ? '-rotate-45' : undefined}>
            {meta.label.slice(0, 2).toUpperCase()}
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-semibold leading-tight text-navy-800" title={node.label}>
            {truncate(node.label || node.id, 24)}
          </p>
          <p className="mt-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-navy-300">
            {meta.label}
            {node.rank && (
              <span className="rounded bg-amber-50 px-1 font-semibold normal-case text-amber-700">#{node.rank}</span>
            )}
          </p>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!invisible" />
    </div>
  );
});
CnaNode.displayName = 'CnaNode';

const nodeTypes = { cna: CnaNode };

/**
 * Deterministic static layout.
 *
 * Seed positions are derived from the node id rather than input order, and the
 * simulation is advanced a fixed number of ticks with no animation loop — so
 * the same graph lays out identically on every run. An investigator who reruns
 * an analysis and sees a different picture will, correctly, stop trusting it.
 */
function layoutOf(nodes, edges) {
  const seedFor = (id) => {
    let h = 0;
    for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) | 0;
    return Math.abs(h);
  };

  const simNodes = nodes.map((n) => {
    const s = seedFor(n.id);
    return { id: n.id, node: n, x: ((s % 1000) - 500) * 1.1, y: ((Math.floor(s / 1000) % 1000) - 500) * 1.1 };
  });

  const present = new Set(simNodes.map((n) => n.id));
  const simLinks = edges
    .filter((e) => present.has(e.source) && present.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  forceSimulation(simNodes)
    .force('link', forceLink(simLinks).id((d) => d.id).distance(165).strength(0.14))
    .force('charge', forceManyBody().strength(-420))
    .force('center', forceCenter(0, 0))
    .force('collide', forceCollide(64))
    .stop()
    .tick(200);

  return simNodes;
}

/**
 * Network graph over the analysis backend's nodes and edges.
 *
 * Positions are computed from the *full* dataset once, so filtering and the
 * timeline replay hide elements without reshuffling the picture underneath.
 */
export function CnaNetworkGraph({
  nodes = [],
  edges = [],
  visibleNodeIds = null,
  visibleEdgeKeys = null,
  highlightIds = null,
  selectedId = null,
  onSelectNode,
  onSelectEdge,
  height = 'h-[560px]',
}) {
  const positioned = useMemo(() => layoutOf(nodes, edges), [nodes, edges]);

  // Capture the React Flow instance via onInit and fit view after layout
  const flowInstance = useRef(null);
  useEffect(() => {
    if (positioned.length && nodes.length && flowInstance.current) {
      flowInstance.current.fitView({ padding: 0.1 });
    }
  }, [positioned, nodes]);

  const rfNodes = useMemo(
    () =>
      positioned
        .filter((p) => !visibleNodeIds || visibleNodeIds.has(p.id))
        .map((p) => ({
          id: p.id,
          type: 'cna',
          position: { x: p.x, y: p.y },
          data: {
            node: p.node,
            selected: selectedId === p.id,
            dimmed: Boolean(highlightIds) && !highlightIds.has(p.id),
            highlighted: Boolean(highlightIds?.has(p.id)),
          },
        })),
    [positioned, visibleNodeIds, highlightIds, selectedId]
  );

  const shownIds = useMemo(() => new Set(rfNodes.map((n) => n.id)), [rfNodes]);

  const rfEdges = useMemo(
    () =>
      edges
        .filter((e) => shownIds.has(e.source) && shownIds.has(e.target))
        .filter((e) => !visibleEdgeKeys || visibleEdgeKeys.has(`${e.source}|${e.target}`))
        .map((e) => {
          const color = cnaEdgeColor(e.types);
          // Corroborated links are drawn thicker; a single-source link stays thin.
          const width = 1 + Math.min(3, (e.independent_sources?.length || 1) - 1) * 0.9;
          return {
            id: `${e.source}|${e.target}`,
            source: e.source,
            target: e.target,
            label: e.types?.map(cnaEdgeLabel).join(' · '),
            labelStyle: { fontSize: 10, fill: 'var(--ink-600)' },
            labelBgStyle: { fill: 'var(--surface)', fillOpacity: 0.85 },
            labelBgPadding: [4, 2],
            labelBgBorderRadius: 4,
            style: { stroke: color, strokeWidth: width, opacity: 0.75 },
            data: e,
          };
        }),
    [edges, shownIds, visibleEdgeKeys]
  );

  return (
    <div className={cn('w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-50/60', height)}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        // remove onlyRenderVisibleElements to ensure nodes render before fitView
        // fitView will be called after layout via effect below
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={(_, n) => onSelectNode?.(n.id)}
        onEdgeClick={(_, e) => onSelectEdge?.(e.data)}
        onPaneClick={() => onSelectNode?.(null)}
        onInit={instance => { flowInstance.current = instance; }}
      >
        <Background gap={18} color="var(--viz-grid)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
