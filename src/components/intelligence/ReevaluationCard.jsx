import { useEffect, useState } from 'react';
import { RefreshCw, Upload } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/modals/Modal';
import { analysisService } from '@/services';

const ICONS = { Share2: RefreshCw, Lightbulb: RefreshCw, CheckCircle2: RefreshCw, Search: RefreshCw };

/**
 * Dynamic Re-evaluation panel — "New Evidence Processed" summary with a
 * What Changed? review modal. Mock presentation values.
 */
export function ReevaluationCard({ investigationId }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let active = true;
    analysisService
      .getReevaluation(investigationId)
      .then((d) => active && setData(d))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [investigationId]);

  if (!data) return null;

  return (
    <Card>
      <CardBody className="flex flex-wrap items-center gap-4 py-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
          <Upload className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold text-navy-900">New evidence processed</p>
          <p className="mt-0.5 text-[12.5px] text-navy-400">
            Evidence <span className="font-mono font-semibold text-navy-600">{data.evidence.refNo}</span> added — NEXUS
            re-evaluated affected analysis.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data.changes.map((c) => (
            <Badge key={c.id} variant="neutral" className="hidden md:inline-flex">
              {c.label}
            </Badge>
          ))}
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            Review Changes
          </Button>
        </div>
      </CardBody>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="What changed?"
        description="Re-evaluation after the latest evidence — mock presentation of a backend service result."
        footer={
          <Button variant="outline" onClick={() => setOpen(false)}>
            Close
          </Button>
        }
      >
        <ul className="space-y-2.5">
          {data.changes.map((c) => {
            const Icon = ICONS[c.icon] || RefreshCw;
            return (
              <li key={c.id} className="flex items-start gap-3 rounded-lg border border-slate-100 p-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-navy-500">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <div>
                  <p className="text-[13px] font-semibold text-navy-800">{c.label}</p>
                  <p className="mt-0.5 text-[12px] text-navy-400">{c.detail}</p>
                </div>
              </li>
            );
          })}
        </ul>
        <p className="mt-4 rounded-lg bg-slate-50 px-3.5 py-2.5 text-[11px] leading-relaxed text-navy-400">
          Re-evaluation is a backend capability. This panel demonstrates how incremental updates would be surfaced for analyst
          review — nothing is recomputed in the browser.
        </p>
      </Modal>
    </Card>
  );
}
