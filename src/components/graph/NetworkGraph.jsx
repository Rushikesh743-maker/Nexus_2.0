import { useMemo } from 'react';
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';
import EntityNode from './EntityNode';
import { computeNetworkLayout } from './layout';
import { RELATIONSHIP_TYPES } from '@/lib/constants';

const nodeTypes = { entity: EntityNode };

function edgeLabel(rel) {
  if (rel.label) return rel.label;
  const meta = RELATIONSHIP_TYPES[rel.type] || RELATIONSHIP_TYPES.associate;
  return meta.label;
}

/**
 * React Flow network graph.
 *
 * - Layout is computed ONCE per full dataset (d3-force, static) — filtering,
 *   expansion and highlight changes never reshuffle positions.
 * - `visibleIds` controls which nodes render (controlled expansion keeps the
 *   graph small); `highlightIds` dims everything outside the highlight set.
 * - `onlyRenderVisibleElements` avoids rendering off-screen nodes.
 *
 * Callbacks: onSelect(nodeId|null), onEdgeSelect(relationship).
 */
export function NetworkGraph({
  entities = [],
  relationships = [],
  evidenceNodes = [],
  evidenceEdges = [],
  visibleIds = null,
  highlightIds = null,
  selectedId,
  onSelect,
  onEdgeSelect,
  height = 'h-[480px]',
}) {
  const layout = useMemo(
    () => computeNetworkLayout([...entities, ...evidenceNodes], [...relationships, ...evidenceEdges]),
    [entities, relationships, evidenceNodes, evidenceEdges]
  );

  const nodes = useMemo(
    () =>
      layout.nodes
        .filter((n) => !visibleIds || visibleIds.has(n.id))
        .map((entity) => ({
          id: entity.id,
          type: 'entity',
          position: { x: entity.x, y: entity.y },
          data: {
            entity,
            dimmed: Boolean(highlightIds) && !highlightIds.has(entity.id),
            highlighted: Boolean(highlightIds?.has(entity.id)),
          },
        })),
    [layout, visibleIds, highlightIds]
  );

  const edges = useMemo(
    () =>
      layout.links
        .filter((l) => !visibleIds || (visibleIds.has(l.sourceId) && visibleIds.has(l.targetId)))
        .map((l) => {
          const meta = RELATIONSHIP_TYPES[l.type] || RELATIONSHIP_TYPES.associate;
          const dim = Boolean(highlightIds) && !(highlightIds.has(l.sourceId) && highlightIds.has(l.targetId));
          return {
            id: l.id,
            source: l.sourceId,
            target: l.targetId,
            label: edgeLabel(l),
            data: { rel: l },
            style: {
              stroke: meta.color,
              strokeWidth: 1 + (l.strength || 50) / 45,
              opacity: dim ? 0.05 : 0.75,
            },
            labelStyle: { fill: '#627d98', fontSize: 10, fontWeight: 500 },
            labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.9 },
            labelBgPadding: [4, 2],
            labelBgBorderRadius: 4,
          };
        }),
    [layout, visibleIds, highlightIds]
  );

  return (
    <div className={`${height} w-full`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => onSelect?.(node.id)}
        onEdgeClick={(_, edge) => onEdgeSelect?.(edge.data.rel)}
        onPaneClick={() => onSelect?.(null)}
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1 }}
        minZoom={0.15}
        maxZoom={1.8}
        nodesConnectable={false}
        nodesDraggable={false}
        panOnScroll
        onlyRenderVisibleElements
        deleteKeyCode={null}
        elevateEdgesOnSelect
      >
        <Background color="#cbd5e1" gap={18} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  );
}
