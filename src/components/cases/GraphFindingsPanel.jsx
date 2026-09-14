/**
 * Network Intelligence findings panel (stage 3).
 *
 * "Analyze Network" triggers the backend engine; findings are explainable
 * results over CONFIRMED data — each one shows the computed reason and can
 * be highlighted in the graph or reviewed/dismissed by the investigator.
 * Nothing here is a confirmed fact; the labels say so.
 *
 * Structure: GraphFindingsPanel = data fetching + state; FindingsBody /
 * FindingRow = pure presentation (independently testable in the frontend
 * sanity harness).
 */
import { useCallback, useState } from 'react';
import { ChevronDown, ChevronRight, Network, ScanSearch, Trash2, UserCheck } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Spinner } from '@/components/ui/LoadingState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { graphService } from '@/services/v1';
import { useToast } from '@/context/ToastContext';
import { FindingEvidenceChain } from '@/components/cases/FindingEvidenceChain';

export const FINDING_TYPE_META = {
  CROSS_CASE_CONNECTION: { label: 'Cross-case', variant: 'violet' },
  BRIDGE_ENTITY: { label: 'Bridge', variant: 'warning' },
  HIDDEN_CONNECTION: { label: 'Hidden connection', variant: 'info' },
  NETWORK_CLUSTER: { label: 'Cluster', variant: 'teal' },
  HIGH_CONNECTIVITY: { label: 'Highly connected', variant: 'neutral' },
  // stage 4 investigation intelligence finding types
  CONTRADICTION: { label: 'Contradiction', variant: 'danger' },
  TIMELINE_INSIGHT: { label: 'Timeline', variant: 'info' },
  GEO_INSIGHT: { label: 'Geospatial', variant: 'teal' },
  INVESTIGATION_GAP: { label: 'Investigation gap', variant: 'warning' },
};

export function findingTypeMeta(type) {
  return FINDING_TYPE_META[type] || { label: type, variant: 'neutral' };
}

/**
 * @param {Function} [reviewFn]   stage-4 panels pass their own review
 *                                endpoint; defaults to the stage-3 one
 * @param {Function} [dismissFn]
 */
export function FindingRow({
  finding, onHighlight, onToast, onChanged,
  reviewFn = graphService.reviewFinding,
  dismissFn = graphService.dismissFinding,
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const meta = findingTypeMeta(finding.finding_type);
  const entityIds = (finding.involved_entity_ids || []).filter(Boolean);

  const act = async (action, successMsg) => {
    setBusy(true);
    try {
      if (action === 'reviewed') await reviewFn(finding.case_id, finding.id);
      else await dismissFn(finding.case_id, finding.id);
      onToast(successMsg, 'success');
      onChanged?.();
    } catch (err) {
      onToast(err.message || 'Review action failed.', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-2.5">
        <button
          type="button"
          className="mt-0.5 shrink-0 text-navy-300 hover:text-navy-600"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Collapse' : 'Expand'}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={meta.variant}>{meta.label}</Badge>
            {finding.stale && <Badge variant="warning">Stale — data changed</Badge>}
            {finding.status !== 'ACTIVE' && (
              <Badge variant={finding.status === 'REVIEWED' ? 'success' : 'danger'}>
                {finding.status === 'REVIEWED' ? 'Reviewed' : 'Dismissed'}
              </Badge>
            )}
          </div>
          <p className="mt-1.5 text-[13px] font-medium leading-snug text-navy-800">{finding.title}</p>
          {finding.summary && <p className="mt-0.5 text-[12px] leading-relaxed text-navy-500">{finding.summary}</p>}

          {open && (
            <div className="mt-2 space-y-2">
              <ul className="space-y-1">
                {(finding.explanation || []).map((line, i) => (
                  <li key={i} className="text-[12px] leading-relaxed text-navy-600">
                    {line}
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-navy-400">
                {finding.supporting_relationship_ids?.length > 0 && (
                  <span>{finding.supporting_relationship_ids.length} supporting relationship(s)</span>
                )}
                {finding.supporting_evidence_ids?.length > 0 && (
                  <span>{finding.supporting_evidence_ids.length} linked evidence record(s)</span>
                )}
                <span className="font-mono">{finding.analysis_method}</span>
              </div>
              {finding.review_note && (
                <p className="text-[11.5px] italic text-navy-400">
                  Review note ({finding.reviewed_by_name || '—'}): {finding.review_note}
                </p>
              )}
              {finding.case_id && (
                <FindingEvidenceChain caseId={finding.case_id} findingId={finding.id} open />
              )}
            </div>
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-6">
        {entityIds.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            icon={ScanSearch}
            onClick={() => onHighlight(entityIds, finding.title)}
          >
            Show in graph
          </Button>
        )}
        {finding.status === 'ACTIVE' && (
          <>
            <Button
              variant="ghost"
              size="sm"
              icon={UserCheck}
              disabled={busy}
              onClick={() => act('reviewed', 'Finding marked as reviewed.')}
            >
              Review
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={Trash2}
              disabled={busy}
              onClick={() => act('dismissed', 'Finding dismissed (kept in audit history).')}
            >
              Dismiss
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

/** Pure presentation of the findings panel body (loading/error/empty/list). */
export function FindingsBody({ loading, data, error, onRetry, analyzed, onHighlight, onToast, onChanged }) {
  return (
    <>
      {loading && !data ? (
        <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-navy-400">
          <Spinner className="h-4 w-4" /> Loading findings…
        </div>
      ) : error && !data ? (
        <ErrorState
          title="Could not load network findings"
          description={error.message}
          onRetry={onRetry}
          compact
        />
      ) : !analyzed ? (
        <EmptyState
          icon={Network}
          title="Not analyzed yet"
          description="Run the analysis to compute cross-case links, bridge entities, hidden connections, clusters and connectivity metrics from the confirmed case data. If the case has little confirmed data, the backend reports “insufficient confirmed graph data” instead of guessing."
        />
      ) : (
        <>
          <div className="border-b border-line-soft px-4 py-2">
            <p className="text-[11.5px] leading-relaxed text-navy-400">
              Findings are analytical results over <span className="font-medium text-navy-600">confirmed data only</span> —
              potential leads for review, never confirmed facts.
            </p>
          </div>
          {data.current_findings.length === 0 ? (
            <EmptyState
              icon={Network}
              title="No significant connection found"
              description="The confirmed graph was analyzed and produced no findings above the documented thresholds."
              compact
            />
          ) : (
            <ul className="max-h-[420px] divide-y divide-line-soft overflow-y-auto">
              {data.current_findings.map((f) => (
                <FindingRow key={f.id} finding={f} onHighlight={onHighlight} onToast={onToast} onChanged={onChanged} />
              ))}
            </ul>
          )}
          {data.stale_findings.length > 0 && (
            <details className="border-t border-line-soft px-4 py-2.5">
              <summary className="cursor-pointer text-[12px] font-medium text-navy-500">
                Previous analysis history ({data.stale_findings.length}) — confirmed data changed since
              </summary>
              <ul className="mt-2 space-y-2">
                {data.stale_findings.map((f) => (
                  <li key={f.id} className="flex flex-wrap items-center gap-1.5 text-[12px] text-navy-400">
                    <Badge variant={findingTypeMeta(f.finding_type).variant}>
                      {findingTypeMeta(f.finding_type).label}
                    </Badge>
                    <span>{f.title}</span>
                    <span className="font-mono text-[10.5px]">{f.graph_version}</span>
                    {f.status !== 'ACTIVE' && (
                      <span className="text-[11px]">({f.status.toLowerCase()})</span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </>
  );
}

export function GraphFindingsPanel({ caseId, onHighlight, onAnalyzedChange, onReloadData }) {
  const toast = useToast();
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);
  const [version, setVersion] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const { data, error, loading, reload } = useCnaResource(
    useCallback(
      async () => {
        const f = await graphService.listGraphFindings(caseId);
        setAnalyzed(f.analyzed);
        setVersion(f.graph_version);
        return f;
      },
      [caseId, reloadKey]
    ),
    [caseId, reloadKey]
  );

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await graphService.analyzeCaseGraph(caseId);
      toast.success(
        res.recomputed
          ? `Network analyzed — ${res.findings.length} finding(s) generated.`
          : 'Confirmed data unchanged — showing the existing analysis.'
      );
      onAnalyzedChange?.();
      onReloadData?.();
      setReloadKey((k) => k + 1);
    } catch (err) {
      if (err.code === 'GRAPH_INSUFFICIENT_DATA') {
        toast.warning('Insufficient confirmed graph data to analyze yet.');
        setReloadKey((k) => k + 1);
        return;
      }
      toast.error(err.message || 'Graph analysis failed.');
    } finally {
      setAnalyzing(false);
    }
  };

  const onActionToast = (msg, kind = 'success') => toast[kind]?.(msg);
  const refresh = () => setReloadKey((k) => k + 1);

  return (
    <Card>
      <CardHeader
        title="Network Intelligence"
        subtitle={
          analyzed
            ? `Graph version ${version} · requires investigator review`
            : 'Not analyzed yet'
        }
        actions={
          <div className="flex items-center gap-2">
            {analyzed && (
              <Badge variant={data?.stale_findings?.length ? 'warning' : 'neutral'}>
                {data?.stale_findings?.length
                  ? `${data.stale_findings.length} stale`
                  : 'up to date'}
              </Badge>
            )}
            <Button
              size="sm"
              icon={analyzing ? null : Network}
              loading={analyzing}
              onClick={runAnalysis}
            >
              {analyzing ? 'Analyzing…' : analyzed ? 'Re-analyze' : 'Analyze Network'}
            </Button>
          </div>
        }
      />
      <FindingsBody
        loading={loading}
        data={data}
        error={error}
        onRetry={reload}
        analyzed={analyzed}
        onHighlight={onHighlight}
        onToast={onActionToast}
        onChanged={refresh}
      />
    </Card>
  );
}
