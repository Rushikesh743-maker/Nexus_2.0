import { useMemo } from 'react';
import { Lightbulb, AlertTriangle, HelpCircle } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { DataTable } from '@/components/tables/DataTable';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService, investigationService } from '@/services/v1';
import { FreshnessBadge } from '@/components/cases/FreshnessBadge';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

/**
 * The three "working state" registers (hypotheses, contradictions, gaps)
 * share one table shape; each page configures the loader and columns.
 * Field names mirror the platform API exactly (see backend/app/schemas/v1.py).
 * Phase 2 (work item G): the header carries the case's analysis freshness
 * badge, so stale results are flagged on the tab itself.
 */
function CaseRecordList({ icon: Icon, title, subtitle, emptyTitle, emptyDescription, load, columns }) {
  const { caseFile: c } = useCaseFile();
  const { data, error, loading, reload } = useCnaResource(() => load(c.id), [c.id]);
  const { data: fresh } = useCnaResource(
    () => investigationService.getInvestigationStatus(c.id).catch(() => null),
    [c.id]
  );
  const cols = useMemo(() => columns.map((col) => (typeof col === 'function' ? col() : col)), [columns]);

  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={subtitle}
        actions={
          <div className="flex items-center gap-2">
            <FreshnessBadge analysis={fresh} />
            <Icon className="h-4 w-4 text-navy-300" aria-hidden />
          </div>
        }
      />
      <DataTable
        columns={cols}
        data={data || []}
        getRowId={(r) => r.id}
        isLoading={loading}
        error={error}
        onRetry={reload}
        emptyIcon={Icon}
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
      />
    </Card>
  );
}

const STATUS_TONE = {
  PROPOSED: 'neutral',
  TESTED: 'info',
  SUPPORTED: 'success',
  REFUTED: 'danger',
  OPEN: 'warning',
  RESOLVED: 'success',
};

const SEVERITY_TONE = { high: 'danger', medium: 'warning', low: 'neutral' };

export function CaseHypothesesPage() {
  return (
    <CaseRecordList
      icon={Lightbulb}
      title="Hypotheses"
      subtitle="Working theories attached to this case"
      emptyTitle="No hypotheses recorded"
      emptyDescription="Hypotheses formulated against this case — seeded from high-severity findings where the pipeline produced them — will appear here."
      load={caseService.listHypotheses}
      columns={[
        {
          key: 'title',
          header: 'Hypothesis',
          render: (r) => <span className="text-[13px] font-medium text-navy-800">{r.title}</span>,
        },
        {
          key: 'description',
          header: 'Statement',
          render: (r) => (
            <span className="line-clamp-2 block max-w-md text-[12px] text-navy-500" title={r.description}>
              {r.description || '—'}
            </span>
          ),
        },
        {
          key: 'score',
          header: 'Score',
          className: 'text-right',
          render: (r) =>
            r.score != null ? (
              <span className="figure text-[12px] text-navy-600">{Math.round(r.score * 100)}%</span>
            ) : (
              '—'
            ),
        },
        {
          key: 'status',
          header: 'Status',
          render: (r) => <Badge variant={STATUS_TONE[r.status] || 'neutral'}>{r.status}</Badge>,
        },
        {
          key: 'created_at',
          header: 'Created',
          render: (r) => <span className="text-[11.5px] text-navy-400">{formatDateTime(r.created_at)}</span>,
        },
      ]}
    />
  );
}

export function CaseContradictionsPage() {
  return (
    <CaseRecordList
      icon={AlertTriangle}
      title="Contradictions"
      subtitle="Conflicting records the system has flagged"
      emptyTitle="No contradictions flagged"
      emptyDescription="Conflicting records detected between sources for this case will appear here."
      load={caseService.listContradictions}
      columns={[
        {
          key: 'title',
          header: 'Contradiction',
          render: (r) => (
            <div className="min-w-0">
              <p className="text-[13px] font-medium text-navy-800">{r.title}</p>
              {r.description && (
                <p className="line-clamp-2 max-w-lg text-[11.5px] text-navy-400" title={r.description}>{r.description}</p>
              )}
            </div>
          ),
        },
        {
          key: 'severity',
          header: 'Severity',
          render: (r) => <Badge variant={SEVERITY_TONE[r.severity] || 'neutral'}>{r.severity}</Badge>,
        },
        {
          key: 'status',
          header: 'Status',
          render: (r) => <Badge variant={STATUS_TONE[r.status] || 'neutral'}>{r.status}</Badge>,
        },
        {
          key: 'created_at',
          header: 'Flagged',
          render: (r) => <span className="text-[11.5px] text-navy-400">{formatDateTime(r.created_at)}</span>,
        },
      ]}
    />
  );
}

export function CaseGapsPage() {
  return (
    <CaseRecordList
      icon={HelpCircle}
      title="Investigation gaps"
      subtitle="Open questions the evidence cannot yet answer"
      emptyTitle="No open gaps"
      emptyDescription="Investigation gaps — things worth establishing that the current evidence does not cover — will appear here."
      load={caseService.listGaps}
      columns={[
        {
          key: 'title',
          header: 'Gap',
          render: (r) => <span className="text-[13px] font-medium text-navy-800">{r.title}</span>,
        },
        {
          key: 'description',
          header: 'Question to resolve',
          render: (r) => (
            <span className="line-clamp-2 block max-w-lg text-[12px] text-navy-500" title={r.description}>
              {r.description || '—'}
            </span>
          ),
        },
        {
          key: 'priority',
          header: 'Priority',
          render: (r) => <Badge variant={SEVERITY_TONE[r.priority] || 'neutral'}>{r.priority}</Badge>,
        },
        {
          key: 'status',
          header: 'Status',
          render: (r) => <Badge variant={STATUS_TONE[r.status] || 'neutral'}>{r.status}</Badge>,
        },
      ]}
    />
  );
}
