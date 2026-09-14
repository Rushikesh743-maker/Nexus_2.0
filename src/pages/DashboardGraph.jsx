import { useMemo } from 'react';
import { NetworkGraph } from '@/components/graph/NetworkGraph';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService, analysisService } from '@/services/v1';
import { toGraphNode, toGraphEdge } from '@/lib/caseTypes';

/**
 * DashboardGraph - renders a network graph for a given case on the dashboard.
 * It fetches entities, relationships and optional graph payload for the case.
 */
export function DashboardGraph({ caseId }) {
  const { data, loading, error } = useCnaResource(async () => {
    if (!caseId) return null;
    const [entities, relationships, graph] = await Promise.all([
      caseService.listEntities(caseId),
      caseService.listRelationships(caseId),
      analysisService.getCaseGraph(caseId).catch(() => null),
    ]);
    return { entities, relationships, graph };
  }, [caseId]);

  const degree = useMemo(() => {
    const d = {};
    (data?.relationships || []).forEach((r) => {
      d[r.source_entity_id] = (d[r.source_entity_id] || 0) + 1;
      d[r.target_entity_id] = (d[r.target_entity_id] || 0) + 1;
    });
    return d;
  }, [data]);

  if (loading || !data) return null;
  if (error) return null;

  const nodes = data.entities.map((e) => toGraphNode(e, degree[e.id] || 0));
  const edges = data.relationships.map(toGraphEdge);

  return <NetworkGraph entities={nodes} relationships={edges} height="h-[320px]" />;
}
