/**
 * Supporting graph-intelligence panels (stage 3): bridge entities,
 * network clusters and cross-case connections. All data is computed from
 * confirmed records by the backend engine; wording stays neutral
 * ("highly connected", "connected group") — never "mastermind" or
 * "criminal gang".
 *
 * Each panel = data-fetching wrapper + exported presentational list
 * (BridgeList / ClusterList / CrossCaseList) so the UI states are
 * independently testable (frontend sanity).
 */
import { useState } from 'react';
import { Building2, GitCompareArrows, Link2, ScanSearch, Waypoints } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Spinner } from '@/components/ui/LoadingState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { graphService } from '@/services/v1';

/** Shared loading/error renderer for the three panels. */
export function PanelState({ res, title, subtitle }) {
  if (res.loading && !res.data) {
    return (
      <Card>
        <CardHeader title={title} subtitle={subtitle} />
        <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-navy-400">
          <Spinner className="h-4 w-4" /> Loading…
        </div>
      </Card>
    );
  }
  if (res.error && !res.data) {
    return (
      <Card>
        <CardHeader title={title} subtitle={subtitle} />
        <ErrorState compact title="Could not load" description={res.error.message} onRetry={res.reload} />
      </Card>
    );
  }
  return null;
}

/* ------------------------------------------------------------ bridges */

export function BridgeList({ bridges, onHighlight }) {
  if (!bridges?.length) {
    return (
      <EmptyState
        compact
        icon={Waypoints}
        title="No significant bridge entities"
        description="No entity scores high enough (articulation + betweenness + cross-case reach) to be reported as a bridge."
      />
    );
  }
  return (
    <ul className="max-h-[300px] divide-y divide-line-soft overflow-y-auto">
      {bridges.map((b) => (
        <li key={b.entity_id} className="px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <p className="text-[13px] font-semibold text-navy-800">{b.name}</p>
              <Badge variant="neutral">{b.entity_type}</Badge>
              {b.is_articulation_point && <Badge variant="warning">articulation</Badge>}
            </div>
            <span className="figure text-[13px] text-navy-600">{b.bridge_score.toFixed(2)}</span>
          </div>
          <p className="mt-1 text-[11.5px] text-navy-400">
            degree {b.degree} · betweenness {b.betweenness.toFixed(3)} ·
            impact {b.connectivity_impact} · {b.cross_case_reach} case{b.cross_case_reach === 1 ? '' : 's'}
          </p>
          <ul className="mt-1.5 space-y-1">
            {b.reasons.map((r, i) => (
              <li key={i} className="text-[11.5px] leading-relaxed text-navy-500">{r}</li>
            ))}
          </ul>
          <div className="mt-2">
            <Button variant="ghost" size="sm" icon={ScanSearch} onClick={() => onHighlight([b.entity_id], b.name)}>
              Show in graph
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function BridgePanel({ caseId, onHighlight }) {
  const res = useCnaResource(() => graphService.getGraphBridges(caseId), [caseId]);
  const pending = <PanelState res={res} title="Bridge Entities" subtitle="Entities that connect regions of the graph" />;
  if (pending) return pending;
  return (
    <Card>
      <CardHeader title="Bridge Entities" subtitle="Entities that connect regions of the graph" />
      <BridgeList bridges={res.data.bridges} onHighlight={onHighlight} />
    </Card>
  );
}

/* ----------------------------------------------------------- clusters */

export function ClusterList({ clusters, onHighlight }) {
  if (!clusters?.length) {
    return (
      <EmptyState
        compact
        icon={Building2}
        title="No clusters found"
        description="The confirmed graph has no connected group of two or more entities."
      />
    );
  }
  return (
    <ul className="max-h-[300px] divide-y divide-line-soft overflow-y-auto">
      {clusters.map((c) => (
        <li key={c.index} className="px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-navy-800">Connected group {c.index}</p>
            <div className="flex items-center gap-1.5">
              {c.cross_case && <Badge variant="violet">cross-case</Badge>}
              <Badge variant="neutral">{c.entity_count} entities · {c.relationship_count} links</Badge>
            </div>
          </div>
          <p className="mt-1 text-[11.5px] leading-relaxed text-navy-500">{c.description}</p>
          <p className="mt-1 text-[11.5px] text-navy-400">
            {Object.entries(c.type_breakdown).map(([t, n]) => `${t} ×${n}`).join(' · ')}
          </p>
          {c.key_bridge && (
            <p className="mt-1 text-[11.5px] text-navy-400">
              Most central member: <span className="font-medium text-navy-600">{c.key_bridge.display_name}</span>
              {' '}({c.key_bridge.bridge_score.toFixed(2)})
            </p>
          )}
          <div className="mt-2">
            <Button variant="ghost" size="sm" icon={ScanSearch}
                    onClick={() => onHighlight(c.entity_ids, `Connected group ${c.index}`)}>
              Show in graph
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ClusterPanel({ caseId, onHighlight }) {
  const res = useCnaResource(() => graphService.getGraphClusters(caseId), [caseId]);
  const pending = <PanelState res={res} title="Network Clusters" subtitle="Connected groups of confirmed entities" />;
  if (pending) return pending;
  return (
    <Card>
      <CardHeader title="Network Clusters" subtitle="Connected groups of confirmed entities" />
      <ClusterList clusters={res.data.clusters} onHighlight={onHighlight} />
    </Card>
  );
}

/* -------------------------------------------------------- cross-case */

export function CrossCaseList({ connections, onHighlight, onOpenCase }) {
  const [openPath, setOpenPath] = useState(null);
  if (!connections?.length) {
    return (
      <EmptyState
        compact
        icon={GitCompareArrows}
        title="No cross-case connections found"
        description="No confirmed entity of this case is shared with any other case."
      />
    );
  }
  return (
    <ul className="max-h-[300px] divide-y divide-line-soft overflow-y-auto">
      {connections.map((c) => (
        <li key={c.case_id} className="px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              className="text-[13px] font-semibold text-navy-800 hover:text-navy-950 hover:underline"
              onClick={() => onOpenCase?.(c.case_id)}
              title="Open case"
            >
              {c.case_number}
            </button>
            <Badge variant={c.connection_kind === 'shared_path' ? 'violet' : 'neutral'}>
              {c.connection_kind === 'shared_path' ? 'shared path' : 'shared entity'}
            </Badge>
          </div>
          <p className="mt-1 text-[11.5px] text-navy-400">
            {c.shared_entities.length} shared confirmed entit{c.shared_entities.length === 1 ? 'y' : 'ies'}: {
              c.shared_entities.slice(0, 4).map((s) => s.name).join(', ')}
            {c.shared_entities.length > 4 && ` (+${c.shared_entities.length - 4} more)`}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {c.example_path.length > 0 && (
              <Button variant="ghost" size="sm" icon={Link2}
                      onClick={() => setOpenPath(openPath === c.case_id ? null : c.case_id)}>
                {openPath === c.case_id ? 'Hide example path' : 'Show example path'}
              </Button>
            )}
            <Button variant="ghost" size="sm" icon={ScanSearch}
                    onClick={() => onHighlight(
                      c.shared_entities.flatMap((s) => s.entity_ids || []),
                      `Cross-case: ${c.case_number}`)}>
              Show in graph
            </Button>
          </div>
          {openPath === c.case_id && c.example_path.length > 0 && (
            <div className="mt-2 rounded border border-line bg-slate-50 px-3 py-2">
              <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12px]">
                {c.example_path.map((step, i) => (
                  <span key={i} className="flex items-center gap-1.5">
                    {i > 0 && <span className="font-mono text-[10.5px] text-navy-400">{c.example_path_relationships[i - 1]}</span>}
                    <span className={step.shared ? 'font-semibold text-navy-800' : 'text-navy-600'}>
                      {step.name}{step.shared && ' [shared]'}
                    </span>
                  </span>
                ))}
              </div>
              <p className="mt-1 text-[11px] text-navy-400">
                {c.evidence_count} linked evidence record(s) on the path — analytical context, not proof.
              </p>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function CrossCasePanel({ caseId, onHighlight, onOpenCase }) {
  const res = useCnaResource(() => graphService.getGraphCrossCase(caseId), [caseId]);
  const pending = <PanelState res={res} title="Cross-Case Connections" subtitle="Confirmed links to other cases" />;
  if (pending) return pending;
  return (
    <Card>
      <CardHeader title="Cross-Case Connections" subtitle="Confirmed links to other cases" />
      <CrossCaseList connections={res.data.connections} onHighlight={onHighlight} onOpenCase={onOpenCase} />
    </Card>
  );
}
