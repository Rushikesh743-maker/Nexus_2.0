import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileText, Link2, User } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { investigationService } from '@/services/v1';

function ChainList({ icon: Icon, title, rows, emptyNote }) {
  if (!rows || rows.length === 0) {
    return (
      <li className="px-3 py-2 text-[11.5px] italic text-navy-400">
        {emptyNote || 'None linked.'}
      </li>
    );
  }
  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((r) => (
        <li key={r.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-1.5">
          <Icon className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
          <span className="figure text-[10.5px] text-navy-300">{r.id}</span>
          <span className="text-[12px] font-medium text-navy-700">{r.label}</span>
          {r.detail && <span className="text-[11px] text-navy-400">{r.detail}</span>}
        </li>
      ))}
    </ul>
  );
}

/**
 * A finding resolved to its full evidence chain (phase 2, work item B+G).
 *
 * Expanding a finding fetches the backend's evidence-chain endpoint and
 * renders every confirmed row behind it — entities, relationships and
 * evidence, each with its source reference. When a link has no rows the
 * chain says so explicitly (``complete: false`` + ``missing`` notes)
 * instead of showing an empty box.
 */
export function FindingEvidenceChain({ caseId, findingId, open }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (data) return;
    let live = true;
    setLoading(true);
    investigationService.getFindingDetail(caseId, findingId)
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setError(e); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [open, caseId, findingId, data]);

  if (!open) return null;
  if (loading) return <div className="px-3 py-2"><PageLoader label="Loading evidence chain…" /></div>;
  if (error && !data) {
    return <div className="px-3 py-2"><ErrorState title="Evidence chain unavailable" description={error.message} /></div>;
  }
  if (!data) return null;

  const chain = data.evidence_chain || {};
  const complete = !!chain.complete;
  return (
    <div className="mt-2 rounded-md border border-line bg-surface-sunken/40">
      <div className="flex flex-wrap items-center gap-2 border-b border-line-soft px-3 py-2">
        {complete
          ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
          : <AlertTriangle className="h-3.5 w-3.5 text-amber-600" aria-hidden />}
        <span className="text-[11.5px] font-medium text-navy-600">Evidence chain</span>
        <Badge variant={complete ? 'success' : 'warning'}>
          {complete ? 'complete' : 'incomplete'}
        </Badge>
        <span className="ml-auto font-mono text-[10px] text-navy-300">
          computed at {String(data.current_graph_version || '').slice(0, 12)}…
        </span>
      </div>
      <div className="grid gap-3 px-3 py-2 md:grid-cols-3">
        <div>
          <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-navy-400">
            Entities ({chain.entities?.length || 0})
          </p>
          <ChainList
            icon={User}
            rows={chain.entities}
            emptyNote="No confirmed entities are linked to this finding."
          />
        </div>
        <div>
          <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-navy-400">
            Relationships ({chain.relationships?.length || 0})
          </p>
          <ChainList
            icon={Link2}
            rows={chain.relationships}
            emptyNote="No confirmed relationships are linked to this finding."
          />
        </div>
        <div>
          <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-navy-400">
            Evidence ({chain.evidence?.length || 0})
          </p>
          <ChainList
            icon={FileText}
            rows={chain.evidence}
            emptyNote="No confirmed evidence is linked to this finding."
          />
        </div>
      </div>
      {chain.missing?.length > 0 && (
        <ul className="border-t border-line-soft px-3 py-2">
          {chain.missing.map((m, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[11.5px] text-amber-700">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
              {m}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default FindingEvidenceChain;
