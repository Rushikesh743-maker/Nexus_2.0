import { ArrowLeftRight, FileText } from 'lucide-react';
import { Drawer } from '@/components/modals/Drawer';
import { Badge } from '@/components/ui/Badge';
import { AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { cnaEdgeLabel, cnaSourceType, formatINR, formatScore } from '@/lib/cna';
import { formatDateTime } from '@/lib/utils';

/**
 * The source records behind one link — the "why do you say this?" panel.
 *
 * Nothing here is summarised: each row is a record the pipeline actually read,
 * with the evidence string it derived and, where the source carries one, the
 * underlying document quoted verbatim.
 */

/** Renders whatever the source document carries, without pretending to more. */
function DocumentBody({ document: doc }) {
  if (!doc) {
    return (
      <p className="mt-2 text-[12px] italic text-navy-300">
        This source is a tabular feed; the individual rows are summarised in the evidence line above.
      </p>
    );
  }

  // A row-count stub is what tabular feeds (CDR, transactions) return.
  if (typeof doc === 'object' && Object.keys(doc).length === 1 && 'rows' in doc) {
    return (
      <p className="mt-2 text-[12px] italic text-navy-300">
        Derived from a tabular feed of {doc.rows} rows; the aggregate is stated above.
      </p>
    );
  }

  const narrative = doc.narrative || doc.observation || doc.text;

  return (
    <div className="mt-2 space-y-2">
      {narrative && (
        <blockquote className="border-l-2 border-teal-300 bg-slate-50 py-2 pl-3 pr-2 text-[12px] leading-relaxed text-navy-600">
          {narrative}
        </blockquote>
      )}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {Object.entries(doc)
          .filter(([k, v]) => !['narrative', 'observation', 'text'].includes(k) && v !== null && v !== '')
          .map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className="text-[10px] font-semibold uppercase tracking-wide text-navy-300">
                {k.replace(/_/g, ' ')}
              </dt>
              <dd className="truncate text-[12px] text-navy-600" title={String(v)}>
                {Array.isArray(v) ? v.join(', ') : String(v)}
              </dd>
            </div>
          ))}
      </dl>
    </div>
  );
}

export function EvidenceTrail({ pair, open, onClose }) {
  const { data, error, loading, reload } = useCnaResource(
    () => cnaService.getEvidence(pair.a, pair.b),
    [pair?.a, pair?.b],
    { enabled: Boolean(open && pair?.a && pair?.b) }
  );

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Why this connection?"
      subtitle={data ? `${data.a} ↔ ${data.b}` : undefined}
      width={600}
    >
      {loading && !data ? (
        <AnalysisSkeleton rows={6} />
      ) : error ? (
        <AnalysisError error={error} onRetry={reload} compact />
      ) : !data ? null : (
        <div className="space-y-4">
          {/* Both endpoints */}
          <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3.5 py-3">
            <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-navy-800">{data.a_label}</span>
            <ArrowLeftRight className="h-4 w-4 shrink-0 text-navy-300" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-right text-[13px] font-semibold text-navy-800">
              {data.b_label}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {(data.types || []).map((t) => (
              <Badge key={t} variant="teal">
                {cnaEdgeLabel(t)}
              </Badge>
            ))}
            <Badge variant="neutral">confidence {formatScore(data.confidence, 2)}</Badge>
            <Badge variant="neutral">
              {data.observations} observation{data.observations === 1 ? '' : 's'}
            </Badge>
            <Badge variant={data.independent_sources?.length > 1 ? 'success' : 'warning'}>
              {data.independent_sources?.length || 0} independent source
              {data.independent_sources?.length === 1 ? '' : 's'}
            </Badge>
          </div>

          {data.independent_sources?.length === 1 && (
            <p className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 text-[12px] leading-relaxed text-amber-800">
              This link rests on a single source system. It is not corroborated independently.
            </p>
          )}

          {/* One card per source record */}
          <div className="space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">
              Source records ({data.sources?.length || 0})
            </p>
            {(data.sources || []).map((src, i) => {
              const meta = cnaSourceType(src.source_type);
              return (
                <div key={`${src.source_id}-${i}`} className="rounded-lg border border-slate-200 p-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex items-center gap-2">
                      <meta.icon className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                      <span className="text-[13px] font-medium text-navy-800">{meta.label}</span>
                      <span className="font-mono text-[11px] text-navy-300">{src.source_id}</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Badge variant="neutral">{cnaEdgeLabel(src.type)}</Badge>
                      <Badge variant="neutral">conf {formatScore(src.confidence, 2)}</Badge>
                    </span>
                  </div>

                  {src.evidence && (
                    <p className="mt-2 text-[12px] leading-relaxed text-navy-600">{src.evidence}</p>
                  )}

                  {/* Source-specific quantities, shown only when present. */}
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-navy-400">
                    {src.timestamp && <span>{formatDateTime(src.timestamp)}</span>}
                    {src.call_count !== undefined && <span>{src.call_count} calls</span>}
                    {src.total_seconds !== undefined && (
                      <span>{Math.round(src.total_seconds / 60)} min total</span>
                    )}
                    {src.amount_inr !== undefined && <span>{formatINR(src.amount_inr)}</span>}
                    {src.cells?.length > 0 && <span>Cells: {src.cells.join(', ')}</span>}
                  </div>

                  <details className="mt-2">
                    <summary className="cursor-pointer text-[12px] font-medium text-navy-500 hover:text-teal-700">
                      <FileText className="mr-1 inline h-3 w-3" aria-hidden />
                      Original record
                    </summary>
                    <DocumentBody document={src.document} />
                  </details>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Drawer>
  );
}
