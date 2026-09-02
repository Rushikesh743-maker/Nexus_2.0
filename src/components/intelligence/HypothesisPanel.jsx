import { useEffect, useState } from 'react';
import { Check, AlertTriangle, ArrowRight, Info } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Drawer } from '@/components/modals/Drawer';
import { analysisService } from '@/services';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

/**
 * Competing Hypotheses — mock presentation. Analysts weigh alternative
 * explanations side by side; confidence values are placeholders until the
 * backend assessment service exists. Neutral language throughout.
 */
export function HypothesisPanel({ investigationId }) {
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    analysisService
      .getHypotheses(investigationId)
      .then((r) => active && setResult(r))
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigationId, reloadKey]);

  if (error) return <ErrorState title="Could not load hypotheses" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!result) return <PageLoader label="Loading hypotheses…" />;

  const open = result.items.find((h) => h.id === openId) || null;

  return (
    <>
      <p className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[12.5px] leading-relaxed text-navy-500">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" aria-hidden />
        Alternative explanations are weighed side by side so a single narrative is never assumed. All confidence values are
        mock placeholders for analyst discussion.
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {result.items.map((h) => (
          <Card key={h.id} className="flex h-full flex-col p-4">
            <div className="flex items-center justify-between">
              <span className="rounded bg-navy-800 px-2 py-0.5 font-mono text-[11px] font-bold text-white">{h.id}</span>
              <Badge variant={h.confidence >= 70 ? 'info' : h.confidence >= 40 ? 'warning' : 'neutral'}>{h.confidence}% confidence</Badge>
            </div>
            <h3 className="mt-2.5 text-[15px] font-semibold text-navy-900">{h.title}</h3>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div className={cn('h-full rounded-full', h.confidence >= 70 ? 'bg-sky-500' : 'bg-amber-500')} style={{ width: `${h.confidence}%` }} />
            </div>
            <dl className="mt-3 flex gap-5 text-[12px]">
              <div>
                <dt className="text-navy-300">Supporting</dt>
                <dd className="font-semibold text-navy-700">{h.supportingCount}</dd>
              </div>
              <div>
                <dt className="text-navy-300">Contradicting</dt>
                <dd className="font-semibold text-navy-700">{h.contradictingCount}</dd>
              </div>
            </dl>
            <Button variant="outline" size="sm" icon={ArrowRight} className="mt-auto pt-0" onClick={() => setOpenId(h.id)}>
              Explore
            </Button>
          </Card>
        ))}
      </div>

      <Drawer
        open={Boolean(open)}
        onClose={() => setOpenId(null)}
        title={open ? `${open.id} · ${open.title}` : ''}
        subtitle="Hypothesis details — mock presentation"
        footer={
          <>
            <Button variant="outline" onClick={() => setOpenId(null)}>
              Close
            </Button>
            <Button onClick={() => navigate(`/investigations/${investigationId}/evidence`)}>View Evidence</Button>
          </>
        }
      >
        {open && (
          <div className="space-y-5">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Supporting</p>
              <ul className="mt-2 space-y-1.5">
                {open.supportingPoints.map((p) => (
                  <li key={p} className="flex items-start gap-2 text-[13px] text-navy-600">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden /> {p}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">Contradicting</p>
              <ul className="mt-2 space-y-1.5">
                {open.contradictingPoints.map((p) => (
                  <li key={p} className="flex items-start gap-2 text-[13px] text-navy-600">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden /> {p}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">
                What would distinguish this hypothesis?
              </p>
              <ul className="mt-2 space-y-1.5">
                {open.distinguishing.map((p) => (
                  <li key={p} className="flex items-start gap-2 text-[13px] text-navy-500">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-navy-300" aria-hidden /> {p}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="flex items-center justify-between text-[12px]">
                <span className="text-navy-400">Current confidence</span>
                <span className="font-semibold text-navy-700">{open.confidence}%</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-sky-500" style={{ width: `${open.confidence}%` }} />
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}
