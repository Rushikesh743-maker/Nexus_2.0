import { Drawer } from '@/components/modals/Drawer';
import { Badge } from '@/components/ui/Badge';
import { AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { cnaSourceType } from '@/lib/cna';

/** Fields rendered as the document body rather than as metadata. */
const NARRATIVE_KEYS = ['narrative', 'observation', 'text', 'brief_facts'];

/**
 * One source document, verbatim.
 *
 * Nothing is asserted that cannot be shown — this is the bottom of the
 * provenance chain, where a claim ends in the record that produced it.
 */
export function DocumentDrawer({ docId, open, onClose }) {
  const { data, error, loading, reload } = useCnaResource(
    () => cnaService.getDocument(docId),
    [docId],
    { enabled: Boolean(open && docId) }
  );

  const record = data?.record || data;
  const sourceMeta = data?.source_type ? cnaSourceType(data.source_type) : null;

  const narrative = NARRATIVE_KEYS.map((k) => record?.[k]).find(Boolean);
  const fields = Object.entries(record || {}).filter(
    ([k, v]) => !NARRATIVE_KEYS.includes(k) && v !== null && v !== '' && typeof v !== 'object'
  );

  return (
    <Drawer open={open} onClose={onClose} title="Source record" subtitle={docId} width={560}>
      {loading && !data ? (
        <AnalysisSkeleton rows={5} />
      ) : error ? (
        <AnalysisError error={error} onRetry={reload} compact />
      ) : !data ? null : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1.5">
            {sourceMeta && (
              <Badge variant="teal">
                <sourceMeta.icon className="h-3 w-3" aria-hidden />
                {sourceMeta.label}
              </Badge>
            )}
            {data.script && (
              <Badge variant={data.script === 'devanagari' ? 'info' : 'neutral'}>
                {data.script === 'devanagari' ? 'Devanagari' : 'Latin'}
              </Badge>
            )}
          </div>

          {narrative ? (
            <blockquote className="whitespace-pre-wrap border-l-2 border-teal-300 bg-slate-50 py-2.5 pl-3.5 pr-3 text-[13px] leading-relaxed text-navy-600">
              {narrative}
            </blockquote>
          ) : (
            <p className="text-[13px] italic text-navy-300">
              This source is a tabular feed; it has no narrative body.
            </p>
          )}

          {fields.length > 0 && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-slate-100 pt-3.5">
              {fields.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="text-[10px] font-semibold uppercase tracking-wide text-navy-300">
                    {key.replace(/_/g, ' ')}
                  </dt>
                  <dd className="mt-0.5 break-words text-[13px] text-navy-700">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}

          {/* Nested arrays/objects (e.g. accused lists) get their own block. */}
          {Object.entries(record || {})
            .filter(([, v]) => typeof v === 'object' && v !== null)
            .map(([key, value]) => (
              <div key={key} className="border-t border-slate-100 pt-3.5">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-300">
                  {key.replace(/_/g, ' ')}
                </p>
                <pre className="mt-1.5 overflow-x-auto rounded-lg bg-slate-50 px-3 py-2 font-mono text-[11px] leading-relaxed text-navy-600">
                  {JSON.stringify(value, null, 2)}
                </pre>
              </div>
            ))}
        </div>
      )}
    </Drawer>
  );
}
