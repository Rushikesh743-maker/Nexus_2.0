import { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Drawer } from '@/components/modals/Drawer';
import { analysisService } from '@/services';

const IMPACT_VARIANT = { High: 'danger', Medium: 'warning', Low: 'neutral' };

/**
 * Investigation Gap Detector — mock presentation. Suggests information that
 * may be worth pursuing through lawful, standard investigative process.
 */
export function GapPanel({ investigationId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    analysisService
      .getGaps(investigationId)
      .then((r) => active && setResult(r))
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigationId, reloadKey]);

  if (error) return <ErrorState title="Could not load gaps" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!result) return <PageLoader label="Detecting information gaps…" />;

  return (
    <div className="space-y-4">
      <p className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-[12.5px] leading-relaxed text-navy-500">
        NEXUS identified information gaps that may be useful for further investigation. Pursue them through standard lawful
        process — gaps are suggestions for analyst review, not directives.
      </p>
      <div className="space-y-3">
        {result.items.map((gap, i) => (
          <Card key={gap.id}>
            <CardBody className="flex items-center gap-4 py-3.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-navy-50 font-mono text-[12px] font-bold text-navy-500">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] font-semibold text-navy-800">{gap.title}</p>
                <p className="mt-0.5 truncate text-[12px] text-navy-400">{gap.description}</p>
              </div>
              <Badge variant={IMPACT_VARIANT[gap.impact] || 'neutral'}>Impact: {gap.impact}</Badge>
              <Button variant="outline" size="sm" icon={ArrowRight} onClick={() => setOpen(gap)}>
                Explore Gap
              </Button>
            </CardBody>
          </Card>
        ))}
      </div>

      <Drawer open={Boolean(open)} onClose={() => setOpen(null)} title={open?.title} subtitle="Investigation gap — mock analysis">
        {open && (
          <div className="space-y-4">
            <Badge variant={IMPACT_VARIANT[open.impact] || 'neutral'}>Impact: {open.impact}</Badge>
            <p className="text-[13px] leading-relaxed text-navy-600">{open.description}</p>
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-4 text-[12.5px] leading-relaxed text-navy-500">
              <p className="font-semibold text-navy-700">Why this matters</p>
              <p className="mt-1">
                Closing this gap would either corroborate or weaken the related assessments, sharpening the evidence picture
                before any action is taken.
              </p>
            </div>
            <p className="text-[11px] leading-relaxed text-navy-300">
              Gap detection runs as a backend service. NEXUS suggests lawful, standard investigative steps only — all actions
              remain with the investigator.
            </p>
          </div>
        )}
      </Drawer>
    </div>
  );
}
