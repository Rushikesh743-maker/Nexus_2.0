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

  const degree = {};
  relationships.forEach((r) => {
    degree[r.sourceId] = (degree[r.sourceId] || 0) + 1;
    degree[r.targetId] = (degree[r.targetId] || 0) + 1;
  });

  return {
    nodes: nodes.map((n) => ({ ...n.entity, x: n.x, y: n.y, degree: degree[n.id] || 0 })),
    links: links.map((l) => ({
      ...l.rel,
      sourceId: typeof l.source === 'object' ? l.source.id : l.source,
      targetId: typeof l.target === 'object' ? l.target.id : l.target,
    })),
  };
}
