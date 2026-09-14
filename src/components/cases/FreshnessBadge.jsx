import { Badge } from '@/components/ui/Badge';
import { INVESTIGATION_STATE_META } from '@/components/cases/InvestigationPanels';

/**
 * Analysis-freshness badge (phase 2, work item G).
 *
 * Every intelligence surface now returns an ``analysis`` block
 * ({ state, graph_version, reason, analyzed, insufficient }). This renders
 * that block so a stale (or not-yet-run) result is never silently presented
 * as current — the tooltip carries the exact reason and the confirmed-data
 * version the state was computed against.
 */
export function FreshnessBadge({ analysis, prefix = 'Analysis', className }) {
  if (!analysis || !analysis.state) return null;
  const meta = INVESTIGATION_STATE_META[analysis.state]
    || { label: analysis.state, variant: 'neutral' };
  const title = [
    `${prefix}: ${meta.label}`,
    analysis.reason,
    analysis.graph_version && `confirmed-data version ${String(analysis.graph_version).slice(0, 12)}…`,
  ].filter(Boolean).join('\n');
  return (
    <Badge variant={meta.variant} dot className={className} title={title}>
      {meta.label}
    </Badge>
  );
}

export default FreshnessBadge;
