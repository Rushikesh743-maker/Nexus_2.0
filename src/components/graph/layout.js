import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force';

/**
 * Compute a deterministic static layout for a network using d3-force.
 * The simulation is advanced manually (no animation loop) and the settled
 * positions are handed to React Flow.
 */
export function computeNetworkLayout(entities = [], relationships = []) {
  const nodes = entities.map((e, i) => ({
    id: e.id,
    entity: e,
    // deterministic seed positions in a rough grid
    x: ((i % 5) * 170) - 340 + (i % 2) * 40,
    y: (Math.floor(i / 5) * 150) - 240,
  }));

  const links = relationships.map((r) => ({
    id: r.id,
    source: r.sourceId,
    target: r.targetId,
    rel: r,
  }));

  forceSimulation(nodes)
    .force('link', forceLink(links).id((d) => d.id).distance(140).strength(0.12))
    .force('charge', forceManyBody().strength(-320))
    .force('center', forceCenter(0, 0))
    .force('collide', forceCollide(58))
    .stop()
    .tick(160);

  // Compute connectivity degree
  const degree = {};
  relationships.forEach((r) => {
    degree[r.sourceId] = (degree[r.sourceId] || 0) + 1;
    degree[r.targetId] = (degree[r.targetId] || 0) + 1;
  });

  // Scale node sizes based on degree (bounded)
  const maxDegree = Math.max(...Object.values(degree), 1);
  const sizeScale = (d) => {
    const t = Math.log1p(d) / Math.log1p(maxDegree);
    const minW = 140, maxW = 240;
    const minH = 44, maxH = 80;
    return { width: minW + t * (maxW - minW), height: minH + t * (maxH - minH) };
  };

  return {
    nodes: nodes.map((n) => {
      const deg = degree[n.id] || 0;
      const { width, height } = sizeScale(deg);
      return { ...n.entity, x: n.x, y: n.y, degree: deg, width, height };
    }),
    links: links.map((l) => ({
      ...l.rel,
      sourceId: typeof l.source === 'object' ? l.source.id : l.source,
      targetId: typeof l.target === 'object' ? l.target.id : l.target,
    })),
  };
}

/**
 * Compute a hierarchical layout using dagre.
 * Nodes are placed according to a top‑down flow, useful for directed graphs.
 */
export function computeHierarchicalLayout(entities = [], relationships = []) {
  // Lazy‑load dagre to avoid bundling it when not needed.
  const dagre = require('dagre');
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));

  // Compute degree map for dynamic node sizing
  const degree = {};
  relationships.forEach((r) => {
    degree[r.sourceId] = (degree[r.sourceId] || 0) + 1;
    degree[r.targetId] = (degree[r.targetId] || 0) + 1;
  });
  const maxDegree = Math.max(...Object.values(degree), 1);
  const sizeScale = (d) => {
    const t = Math.log1p(d) / Math.log1p(maxDegree);
    const minW = 140, maxW = 240;
    const minH = 44, maxH = 80;
    return { width: minW + t * (maxW - minW), height: minH + t * (maxH - minH) };
  };
  // Add nodes with scaled sizes.
  entities.forEach((e) => {
    const deg = degree[e.id] || 0;
    const { width, height } = sizeScale(deg);
    g.setNode(e.id, { width, height, label: e.name });
  });

  // Add edges.
  relationships.forEach((r) => {
    g.setEdge(r.sourceId, r.targetId, { id: r.id, label: r.type });
  });

  dagre.layout(g);

  const nodes = entities.map((e) => {
    const n = g.node(e.id);
    return { ...e, x: n.x, y: n.y };
  });

  const links = relationships.map((r) => {
    const e = g.edge(r.sourceId, r.targetId);
    return { ...r, sourceId: r.sourceId, targetId: r.targetId };
  });

  return { nodes, links };
}
