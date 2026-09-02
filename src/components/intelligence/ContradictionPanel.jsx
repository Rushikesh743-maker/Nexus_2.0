import { useEffect, useState } from 'react';
import { Check, AlertTriangle, ArrowRight, FileText, Eye } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Drawer } from '@/components/modals/Drawer';
import { WhyDrawer } from './WhyDrawer';
import { buildChain } from './EvidenceChain';
import { analysisService } from '@/services';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

/**
 * Contradiction Engine — mock presentation. Supporting vs contradicting
 * evidence per relationship, confidence revision and per-item "why is this
 * contradictory?" details. No contradiction logic runs here.
 */
export function ContradictionPanel({ investigationId }) {
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [detail, setDetail] = useState(null); // { contradiction, item }
  const [why, setWhy] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    analysisService
      .getContradictions(investigationId)
      .then((r) => active && setResult(r))
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigationId, reloadKey]);

  const openEvidence = (record) =>
    navigate(`/investigations/${investigationId}/evidence?evidence=${record.id}`);

  if (error) return <ErrorState title="Could not load contradiction analysis" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!result) return <PageLoader label="Comparing evidence…" />;
  if (result.items.length === 0)
    return (
      <Card>
        <EmptyState title="No contradictions flagged" description="When conflicting records are detected, they appear here for review." />
      </Card>
    );

  return (
    <div className="space-y-4">
      {result.items.map((c) => (
        <Card key={c.id}>
          <CardBody className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Contradiction Analysis</p>
              <Badge variant="warning" dot>
                Conflicting evidence detected
              </Badge>
            </div>
            <p className="text-[15px] font-semibold text-navy-900">
              {c.sourceName} <span className="text-navy-300">↔</span> {c.targetName}
              <span className="ml-2 text-[12px] font-medium text-navy-400">{c.relationshipLabel}</span>
            </p>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-3">
                <p className="text-[11px] font-semibold text-emerald-700">Supporting evidence ({c.supporting.length})</p>
                <ul className="mt-2 space-y-1.5">
                  {c.supporting.map((s) => (
                    <li key={s.id}>
                      <button type="button" onClick={() => openEvidence(s)} className="flex items-center gap-1.5 text-[12.5px] font-medium text-navy-600 hover:text-teal-700">
                        <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                        <span className="rounded bg-white px-1 font-mono text-[10px] font-semibold text-navy-500 ring-1 ring-emerald-100">{s.refNo}</span>
                        <span className="truncate">{s.title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-3">
                <p className="text-[11px] font-semibold text-amber-700">Contradicting evidence ({c.contradicting.length})</p>
                <ul className="mt-2 space-y-1.5">
                  {c.contradicting.map((s) => (
                    <li key={s.id}>
                      <button type="button" onClick={() => setDetail({ contradiction: c, item: s })} className="flex items-center gap-1.5 text-[12.5px] font-medium text-navy-600 hover:text-amber-700">
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-600" aria-hidden />
                        <span className="rounded bg-white px-1 font-mono text-[10px] font-semibold text-amber-700 ring-1 ring-amber-200">{s.refNo}</span>
                        <span className="truncate">{s.title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Assessment */}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-slate-200 p-3">
              <span className="text-[12px] text-navy-400">
                Assessment · Previous <span className="ml-1 font-semibold text-navy-700">{c.confidenceBefore}%</span>
              </span>
              <span className="text-[12px] text-navy-400">
                Current <span className="ml-1 font-semibold text-amber-700">{c.confidenceAfter}%</span>
              </span>
              <div className="h-1.5 min-w-[120px] flex-1 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-amber-500" style={{ width: `${c.confidenceAfter}%` }} />
              </div>
              <Button variant="ghost" size="sm" onClick={() => setWhy(c)}>
                Why?
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" icon={Eye} onClick={() => openEvidence(c.supporting[0] || c.contradicting[0])}>
                View Supporting Evidence
              </Button>
              <Button variant="outline" size="sm" icon={AlertTriangle} onClick={() => setDetail({ contradiction: c, item: c.contradicting[0] })}>
                View Contradicting Evidence
              </Button>
            </div>
          </CardBody>
        </Card>
      ))}

      {/* Contradiction details */}
      <Drawer
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title="Why is this contradictory?"
        subtitle={detail ? `Evidence ${detail.item.refNo}` : ''}
        footer={
          <>
            <Button variant="outline" onClick={() => setDetail(null)}>
              Close
            </Button>
            <Button icon={FileText} onClick={() => detail && openEvidence(detail.item)}>
              View Source
            </Button>
          </>
        }
      >
        {detail && (
          <div className="space-y-4">
            <dl className="space-y-3 rounded-xl border border-slate-200 p-4">
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Source</dt>
                <dd className="mt-0.5 text-[13px] text-navy-700">{detail.item.source}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Statement</dt>
                <dd className="mt-0.5 text-[13px] italic leading-relaxed text-navy-600">{detail.item.statement}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Conflict</dt>
                <dd className="mt-0.5 text-[13px] text-navy-700">{detail.item.conflict}</dd>
              </div>
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Related evidence</dt>
                <dd className="mt-0.5 text-[13px] text-navy-700">{detail.item.relatedRefNo}</dd>
              </div>
            </dl>
            <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3.5">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-navy-300">Relationship confidence</p>
                <p className="mt-0.5 text-[13px] text-navy-600">
                  <span className="font-semibold">{detail.contradiction.confidenceBefore}%</span> →{' '}
                  <span className={cn('font-semibold', 'text-amber-700')}>{detail.contradiction.confidenceAfter}%</span>
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setWhy(detail.contradiction);
                  setDetail(null);
                }}
              >
                Why?
              </Button>
            </div>
            <p className="text-[11px] leading-relaxed text-navy-300">
              Excerpts are fictional mock content. Contradiction detection runs as a backend service — this screen presents its
              results for analyst review.
            </p>
          </div>
        )}
      </Drawer>

      {/* Global Why? provenance */}
      <WhyDrawer
        open={Boolean(why)}
        onClose={() => setWhy(null)}
        title="Why this contradiction assessment?"
        badge={why ? `${why.sourceName} ↔ ${why.targetName}` : ''}
        description="The assessment compares records that cannot both be true at the recorded times, and revises relationship confidence accordingly."
        chain={
          why
            ? buildChain({ source: { name: why.sourceName }, target: { name: why.targetName }, relationship: { type: 'communication', label: why.relationshipLabel, strength: why.confidenceBefore }, evidence: null })
            : []
        }
      />
    </div>
  );
}
