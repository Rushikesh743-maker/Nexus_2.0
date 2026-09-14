import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, FileSearch } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

/**
 * Case relationships — the CONFIRMED typed links of this case. Every row
 * carries its provenance exactly as persisted at confirmation time: the
 * source document, the supporting snippet, the candidate id and, when
 * linked, the supporting evidence row (deep-linkable from the Evidence
 * tab). Nothing is auto-confirmed — these rows exist because the
 * investigator confirmed each candidate.
 */
export function CaseRelationshipsPage() {
  const { caseFile: c } = useCaseFile();
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => caseService.listRelationships(c.id), [c.id]),
    [c.id]
  );

  if (loading && !data) return <PageLoader label="Loading relationships…" />;
  if (error && !data) return <ErrorState title="Relationships unavailable" description={error.message} onRetry={reload} />;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-display text-[17px] text-navy-900">Relationships</h2>
        <p className="text-[12px] text-navy-400">
          {data?.length ?? 0} confirmed in this case · every row is traceable to the document it came from.
        </p>
      </div>

      {data?.length ? (
        <Card>
          <CardHeader title="Confirmed links" subtitle="Relationship candidates that the investigator confirmed" />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12.5px]">
              <thead>
                <tr className="border-b border-line text-[10.5px] uppercase tracking-[0.08em] text-navy-300">
                  <th className="px-4 py-2 font-medium">From</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">To</th>
                  <th className="px-3 py-2 font-medium">Source document</th>
                  <th className="px-3 py-2 font-medium">Supporting snippet</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {(data || []).map((r) => {
                  const meta = r.metadata || {};
                  return (
                    <tr key={r.id} className="hover:bg-slate-50/60">
                      <td className="px-4 py-2.5 font-medium text-navy-800">{r.source_label}</td>
                      <td className="px-3 py-2.5">
                        <span className="figure rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-navy-600">
                          {r.relationship_type}
                        </span>
                        {typeof r.confidence === 'number' && (
                          <span className="figure ml-1.5 text-[10px] text-navy-300">
                            {(r.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 font-medium text-navy-800">{r.target_label}</td>
                      <td className="px-3 py-2.5 text-navy-500">
                        {meta.source_document_name || meta.source_document_id
                          ? meta.source_document_name || `document ${meta.source_document_id}`
                          : <span className="text-navy-300">seeded record</span>}
                      </td>
                      <td className="max-w-[280px] truncate px-3 py-2.5 text-navy-400" title={meta.source_snippet || undefined}>
                        {meta.source_snippet || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {meta.source_evidence_id && (
                            <Link
                              to={`/cases/${c.id}/evidence?reference=${meta.source_evidence_id}`}
                              className="flex items-center gap-1 text-[11.5px] font-medium text-navy-500 hover:text-navy-900"
                            >
                              <FileSearch className="h-3 w-3" aria-hidden /> Evidence
                            </Link>
                          )}
                          <Link
                            to={`/cases/${c.id}/graph?relationship=${r.id}`}
                            className="flex items-center gap-1 text-[11.5px] font-medium text-navy-500 hover:text-navy-900"
                          >
                            <ArrowRight className="h-3 w-3" aria-hidden /> Graph
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line-soft px-4 py-2.5 text-[11px] text-navy-300">
            Confirmed {formatDateTime((data || [])[0]?.created_at)} and later · rows without a source document are
            seeded demonstration records, and say so.
          </p>
        </Card>
      ) : (
        <EmptyState
          icon={ArrowRight}
          title="No confirmed relationships yet"
          description="Confirm relationship candidates on the Review tab — each one is only created when a document (or its columns) explicitly states the link."
        />
      )}
    </div>
  );
}
