import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ScrollText,
  Play,
  Loader2,
  AlertTriangle,
  Lightbulb,
  HelpCircle,
  History,
} from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useToast } from '@/context/ToastContext';
import { useCnaResource } from '@/hooks/useCnaResource';
import { analysisService, investigationService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

const STATE_LABEL = {
  'not-analyzed': 'Not analyzed yet',
  'up-to-date': 'Up to date',
  stale: 'Stale — data changed',
  insufficient: 'Insufficient confirmed data',
};

/**
 * Case reports — the case's state of record, all from the database:
 * the full count summary, the analysis state, current findings,
 * hypotheses, gaps and the case-scoped audit trail (who did what, when).
 * Nothing on this page is computed client-side or invented.
 */
export function CaseReportsPage() {
  const { caseFile: c } = useCaseFile();
  const toast = useToast();
  const [reloadKey, setReloadKey] = useState(0);
  const [running, setRunning] = useState(false);

  const { data: summary, error: summaryError, loading: summaryLoading, reload: reloadSummary } = useCnaResource(
    useCallback(() => analysisService.getCaseSummary(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );
  const { data: status } = useCnaResource(
    useCallback(() => analysisService.getAnalysisStatus(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );
  const { data: findingsData } = useCnaResource(
    useCallback(() => investigationService.listInvestigationFindings(c.id, { includeStale: true }), [c.id, reloadKey]),
    [c.id, reloadKey]
  );
  const { data: hypotheses } = useCnaResource(
    useCallback(() => investigationService.listHypotheses(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );
  const { data: gaps } = useCnaResource(
    useCallback(() => investigationService.listInvestigationGaps(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );
  const { data: audit } = useCnaResource(
    useCallback(() => analysisService.getCaseAudit(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );

  const runIntelligence = async () => {
    setRunning(true);
    try {
      const res = await analysisService.runCaseAnalysis(c.id);
      if (res.status === 'completed') {
        toast.success(`Analysis complete — ${res.findings_count} finding(s).`);
      } else {
        toast.info(res.reason || res.status);
      }
      setReloadKey((k) => k + 1);
    } catch (err) {
      toast.error(err.message || 'Analysis run failed.');
    } finally {
      setRunning(false);
    }
  };

  if (summaryLoading && !summary) return <PageLoader label="Compiling case report…" />;
  if (summaryError && !summary) {
    return <ErrorState title="Report unavailable" description={summaryError.message} onRetry={reloadSummary} />;
  }

  const counts = summary?.counts || {};
  const findings = findingsData?.current_findings || [];
  const stale = findingsData?.stale_findings || [];
  const state = status?.state || 'not-analyzed';

  const COUNT_CELLS = [
    ['Documents', counts.documents, `/cases/${c.id}/documents`],
    ['Entities', counts.entities, `/cases/${c.id}/entities`],
    ['Relationships', counts.relationships, `/cases/${c.id}/relationships`],
    ['Evidence', counts.evidence, `/cases/${c.id}/evidence`],
    ['Timeline events', counts.timeline_events, `/cases/${c.id}/timeline`],
    ['Locations', counts.locations, `/cases/${c.id}/map`],
    ['Findings (current)', counts.findings_current, `/cases/${c.id}/investigation`],
    ['Contradictions', counts.contradictions, `/cases/${c.id}/contradictions`],
    ['Hypotheses', counts.hypotheses, `/cases/${c.id}/hypotheses`],
    ['Claims', counts.claims, `/cases/${c.id}/review`],
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-display text-[17px] text-navy-900">Case report</h2>
          <p className="text-[12px] text-navy-400">
            {summary?.case_number} · compiled from the case record at {formatDateTime(new Date())}
          </p>
        </div>
        <Button icon={running ? Loader2 : Play} loading={running} onClick={runIntelligence}>
          Run intelligence
        </Button>
      </div>

      {/* analysis state strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-slate-50/70 px-4 py-2.5">
        <span className="flex items-center gap-1.5 text-[12px] font-medium text-navy-700">
          <History className="h-3.5 w-3.5 text-navy-400" aria-hidden />
          {STATE_LABEL[state] || state}
        </span>
        {status?.graph_version && (
          <span className="figure text-[10.5px] text-navy-400">snapshot {status.graph_version}</span>
        )}
        {summary?.analysis?.last_analyzed && (
          <span className="text-[10.5px] text-navy-400">last analyzed {formatDateTime(summary.analysis.last_analyzed)}</span>
        )}
        {state === 'stale' && (
          <span className="text-[11px] font-medium text-amber-600">
            {status?.findings?.stale} finding(s) from the previous snapshot are kept as stale — re-run to refresh.
          </span>
        )}
        {state === 'insufficient' && (
          <span className="text-[11px] text-navy-500">{status?.reason}</span>
        )}
      </div>

      {/* counts */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-5">
        {COUNT_CELLS.map(([label, value, to]) => (
          <Link key={label} to={to} className="group bg-white px-3 py-2.5 transition-colors hover:bg-slate-50">
            <p className="figure text-[19px] leading-tight text-navy-900 group-hover:text-navy-950">{value ?? 0}</p>
            <p className="text-[10.5px] text-navy-400">{label}</p>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {/* findings */}
        <Card>
          <CardHeader
            title={`Findings (${findings.length} current${stale.length ? `, ${stale.length} stale` : ''})`}
            subtitle="Computed results of the intelligence run — each is explainable and evidence-backed"
            actions={<AlertTriangle className="h-4 w-4 text-navy-300" aria-hidden />}
          />
          {findings.length ? (
            <ul className="divide-y divide-line-soft">
              {findings.slice(0, 10).map((f) => (
                <li key={f.id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="min-w-0 truncate text-[12.5px] font-medium text-navy-800">{f.title}</p>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {f.details?.severity && <Badge variant={f.details.severity === 'HIGH' ? 'danger' : 'warning'}>{f.details.severity}</Badge>}
                      <Badge variant="default">{f.finding_type.replace('_', ' ')}</Badge>
                    </span>
                  </div>
                  {f.summary && <p className="mt-0.5 text-[11.5px] text-navy-500">{f.summary}</p>}
                </li>
              ))}
              {findings.length > 10 && (
                <li className="px-4 py-2 text-[11px] text-navy-400">
                  +{findings.length - 10} more on the <Link to={`/cases/${c.id}/investigation`} className="font-medium text-navy-600 hover:text-navy-900">Intelligence</Link> tab
                </li>
              )}
            </ul>
          ) : (
            <EmptyState compact icon={AlertTriangle} title="No findings yet" description="Run the intelligence to compute findings from the confirmed case data." />
          )}
        </Card>

        {/* hypotheses + gaps */}
        <div className="space-y-4">
          <Card>
            <CardHeader
              title={`Hypotheses (${hypotheses?.length ?? 0})`}
              actions={<Lightbulb className="h-4 w-4 text-navy-300" aria-hidden />}
            />
            {(hypotheses || []).length ? (
              <ul className="divide-y divide-line-soft">
                {hypotheses.slice(0, 6).map((h) => (
                  <li key={h.id} className="px-4 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="min-w-0 truncate text-[12.5px] font-medium text-navy-800">{h.title}</p>
                      <span className="flex shrink-0 items-center gap-1.5">
                        {h.confidence_band && <Badge variant={h.confidence_band === 'HIGH' ? 'danger' : 'warning'}>{h.confidence_band}</Badge>}
                        <span className="figure text-[10.5px] text-navy-400">{(h.analytical_score * 100).toFixed(0)}</span>
                      </span>
                    </div>
                    <p className="figure mt-0.5 text-[10.5px] text-navy-300">{h.hypothesis_type.replace(/_/g, ' ').toLowerCase()}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState compact icon={Lightbulb} title="No hypotheses yet" description="Competing explanations are generated when the intelligence runs." />
            )}
          </Card>

          <Card>
            <CardHeader
              title={`Open gaps (${gaps?.length ?? 0})`}
              actions={<HelpCircle className="h-4 w-4 text-navy-300" aria-hidden />}
            />
            {(gaps || []).length ? (
              <ul className="divide-y divide-line-soft">
                {gaps.slice(0, 6).map((g) => (
                  <li key={g.id} className="px-4 py-2.5">
                    <p className="text-[12.5px] font-medium text-navy-800">{g.title}</p>
                    {g.description && <p className="mt-0.5 text-[11.5px] text-navy-500">{g.description}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState compact icon={HelpCircle} title="No gaps detected" description="Gaps in the confirmed record surface here when the intelligence runs." />
            )}
          </Card>
        </div>
      </div>

      {/* audit trail */}
      <Card>
        <CardHeader
          title={`Audit trail (${audit?.count ?? 0} entries)`}
          subtitle="Case-scoped record of the workflow: creation, uploads, processing, confirmations, graph builds, analysis runs"
          actions={<ScrollText className="h-4 w-4 text-navy-300" aria-hidden />}
        />
        <div className="max-h-[360px] overflow-y-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-line text-[10.5px] uppercase tracking-[0.08em] text-navy-300">
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-3 py-2 font-medium">Action</th>
                <th className="px-3 py-2 font-medium">Resource</th>
                <th className="px-4 py-2 font-medium">User</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {(audit?.entries || []).map((e) => (
                <tr key={e.id}>
                  <td className="figure whitespace-nowrap px-4 py-1.5 text-navy-400">{formatDateTime(e.timestamp)}</td>
                  <td className="figure px-3 py-1.5 text-navy-700">{e.action}</td>
                  <td className="px-3 py-1.5 text-navy-500">
                    {e.resource_type}{e.resource_id ? ` #${e.resource_id}` : ''}
                  </td>
                  <td className="px-4 py-1.5 text-navy-500">{e.user || 'system'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
