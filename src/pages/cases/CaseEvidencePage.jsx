import { useMemo } from 'react';
import { FileText } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { DataTable } from '@/components/tables/DataTable';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';
import { DocumentsPanel } from '@/components/cases/DocumentsPanel';

/** Case evidence: the document register (upload/processing/review) plus
 *  the evidence items the case has on record.
 *
 * Deep links: /cases/:id/evidence?evidence=<id> (copilot citations and
 * the findings pages) or ?reference=<id> (relationship rows) — the id
 * highlights that row and disables paging so the cited record is always
 * visible. */
export function CaseEvidencePage() {
  const { caseFile: c } = useCaseFile();
  const [params] = useSearchParams();
  const focusParam = params.get('evidence') || params.get('reference');
  const focusId = focusParam ? Number(focusParam) : null;
  // phase 2: ?entity=<id> — the entity focus panel's "View in Evidence":
  // the register is filtered to the evidence confirmed for that entity
  // (fetched from the profile endpoint, no invented links).
  const entityFilter = params.get('entity') ? Number(params.get('entity')) : null;
  const { data: items, error, loading, reload } = useCnaResource(
    () => caseService.listEvidence(c.id),
    [c.id]
  );
  const { data: profile } = useCnaResource(
    () => (entityFilter != null ? caseService.getEntityProfile(c.id, entityFilter) : Promise.resolve(null)),
    [c.id, entityFilter]
  );
  const entityEvidenceIds = useMemo(
    () => new Set((profile?.evidence || []).map((e) => e.id)),
    [profile]
  );
  const visibleItems = useMemo(() => {
    if (!items) return items;
    if (entityFilter == null || entityEvidenceIds.size === 0) return items;
    return items.filter((e) => entityEvidenceIds.has(e.id));
  }, [items, entityFilter, entityEvidenceIds]);

  const columns = useMemo(
    () => [
      {
        key: 'description',
        header: 'Evidence',
        render: (r) => (
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-navy-800" title={r.description}>{r.description}</p>
            <p className="figure text-[10.5px] text-navy-400">{r.source_reference || `evidence #${r.id}`}</p>
          </div>
        ),
      },
      { key: 'evidence_type', header: 'Type', render: (r) => <Badge variant="neutral">{r.evidence_type}</Badge> },
      {
        key: 'document_filename',
        header: 'Document',
        render: (r) =>
          r.document_id ? (
            <Link
              to={`/cases/${c.id}/documents/${r.document_id}`}
              className="figure block max-w-[220px] truncate text-[11.5px] text-accent hover:underline"
              title={`Open ${r.document_filename || 'document'}`}
            >
              {r.document_filename || `document #${r.document_id}`}
            </Link>
          ) : (
            <span className="figure block max-w-[220px] truncate text-[11.5px] text-navy-500" title={r.document_filename}>
              {r.document_filename || '—'}
            </span>
          ),
      },
      {
        key: 'confidence',
        header: 'Confidence',
        className: 'text-right',
        render: (r) =>
          r.confidence != null ? (
            <span className="figure text-[12px] text-navy-600">{Math.round(r.confidence * 100)}%</span>
          ) : (
            <span className="text-[11.5px] text-navy-300">recorded</span>
          ),
      },
      {
        key: 'collected_at',
        header: 'Collected',
        render: (r) => <span className="text-[12px] text-navy-400">{r.collected_at ? formatDateTime(r.collected_at) : '—'}</span>,
      },
    ],
    []
  );

  return (
    <div className="space-y-5">
      <DocumentsPanel caseFile={c} />

      {entityFilter != null && (
        <div className="flex items-center gap-2 rounded-md border border-line bg-slate-50/70 px-3.5 py-2 text-[12px] text-navy-600">
          <span>
            Showing evidence confirmed for entity
            {' '}<span className="figure font-medium text-navy-800">#{entityFilter}</span>
            {profile?.entity?.canonical_name && <> — {profile.entity.canonical_name}</>}
            .
          </span>
          <Link to={`/cases/${c.id}/evidence`} className="ml-auto font-medium text-accent hover:underline">
            Clear
          </Link>
        </div>
      )}

      {focusId != null && (
        <div className="flex items-center gap-2 rounded-md border border-line bg-slate-50/70 px-3.5 py-2 text-[12px] text-navy-600">
          <span>
            Highlighting evidence <span className="figure font-medium text-navy-800">#{focusId}</span>
            {' '}from the citation.
          </span>
          <Link to={`/cases/${c.id}/evidence`} className="ml-auto font-medium text-accent hover:underline">
            Clear
          </Link>
        </div>
      )}

      <Card>
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[14px] font-semibold text-navy-900">Evidence register</h2>
          <p className="figure text-[11px] text-navy-400">
            Every evidence item tied to this case, including evidence generated by accepted extractions
          </p>
        </div>
        <DataTable
          columns={columns}
          data={visibleItems || []}
          getRowId={(r) => r.id}
          isLoading={loading}
          error={error}
          onRetry={reload}
          selectedRowId={focusId}
          paginated={focusId == null}
          emptyIcon={FileText}
          emptyTitle="No evidence recorded"
          emptyDescription="Evidence items linked to documents in this case will appear here."
        />
      </Card>
    </div>
  );
}
