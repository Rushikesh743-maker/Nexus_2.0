import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { Modal } from '@/components/modals/Modal';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Logo } from '@/components/ui/Logo';
import { PageLoader } from '@/components/ui/LoadingState';
import { EvidenceChain } from '@/components/intelligence/EvidenceChain';
import { analysisService, investigationService } from '@/services';
import { useToast } from '@/context/ToastContext';
import { formatDate, timeAgo } from '@/lib/utils';

/**
 * Professional report preview — a structured, print-style document assembled
 * from the case + mock analysis services. Export is a mock action until the
 * backend document service exists.
 */
export function ReportPreviewModal({ open, onClose, investigation }) {
  const toast = useToast();
  const [summary, setSummary] = useState(null);
  const [stats, setStats] = useState(null);
  const [contradictions, setContradictions] = useState(null);
  const [hypotheses, setHypotheses] = useState(null);
  const [gaps, setGaps] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    investigationService.getById(investigation.id).then((inv) => active && setStats(inv.stats));
    analysisService.getSummary(investigation.id).then((s) => active && setSummary(s));
    analysisService.getContradictions(investigation.id).then((r) => active && setContradictions(r.items));
    analysisService.getHypotheses(investigation.id).then((r) => active && setHypotheses(r.items));
    analysisService.getGaps(investigation.id).then((r) => active && setGaps(r.items));
    return () => {
      active = false;
    };
  }, [open, investigation.id]);

  const exportPdf = () => {
    toast.info('Export needs the document service', 'PDF generation runs server-side — mock action in this build.');
  };

  const topContradiction = contradictions?.[0];

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Report preview"
      description={`${investigation.code} · read-only document view`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button icon={Download} onClick={exportPdf}>
            Export PDF
          </Button>
        </>
      }
    >
      {!stats || !summary ? (
        <PageLoader label="Assembling report…" />
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white p-6 sm:p-8">
          {/* Letterhead */}
          <div className="flex items-start justify-between gap-4 border-b-2 border-navy-900 pb-4">
            <Logo withTagline />
            <div className="text-right text-[11px] text-navy-400">
              <p className="font-mono font-semibold text-navy-600">{investigation.code}</p>
              <p className="mt-0.5">Generated: {formatDate(new Date())}</p>
              <p>
                Status: <span className="font-medium text-navy-600">{investigation.status === 'active' ? 'Active' : investigation.status}</span>
              </p>
            </div>
          </div>

          <h1 className="mt-6 text-lg font-semibold text-navy-900">{investigation.title}</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-navy-500">{investigation.description}</p>

          {/* Summary */}
          <h2 className="mt-6 text-[13px] font-bold uppercase tracking-wide text-navy-700">Investigation summary</h2>
          <dl className="mt-2 grid grid-cols-3 gap-3 sm:grid-cols-5">
            {[
              ['Entities', stats.entities],
              ['Relationships', stats.relationships],
              ['Evidence', stats.evidence],
              ['Events', stats.events],
              ['Locations', stats.locations],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-slate-200 p-2.5 text-center">
                <dd className="text-lg font-semibold text-navy-900">{value}</dd>
                <dt className="text-[10px] font-medium uppercase tracking-wide text-navy-300">{label}</dt>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[12px] text-navy-400">
            Lead: {investigation.lead?.name || '—'} · Jurisdiction: {investigation.jurisdiction || '—'} · Timeline span covers{' '}
            {stats.events} recorded events; last activity {timeAgo(investigation.updatedAt)}.
          </p>

          {/* Key analytical findings */}
          <h2 className="mt-6 text-[13px] font-bold uppercase tracking-wide text-navy-700">Key analytical findings</h2>
          <p className="mt-1 text-[11px] text-navy-300">Mock analysis values — produced by backend services in production.</p>

          <div className="mt-3 space-y-4 text-[12.5px] leading-relaxed text-navy-600">
            <div className="rounded-lg border border-slate-200 p-3.5">
              <p className="flex items-center justify-between gap-2 font-semibold text-navy-800">
                Evidence confidence <Badge variant="info">{summary.confidence}%</Badge>
              </p>
              {topContradiction && (
                <p className="mt-1.5">
                  <span className="font-medium">Contradiction:</span> {topContradiction.sourceName} ↔ {topContradiction.targetName} —{' '}
                  {topContradiction.contradicting.length} conflicting record(s); confidence revised{' '}
                  {topContradiction.confidenceBefore}% → {topContradiction.confidenceAfter}%.
                </p>
              )}
            </div>

            {hypotheses && (
              <div className="rounded-lg border border-slate-200 p-3.5">
                <p className="font-semibold text-navy-800">Hypotheses</p>
                <ul className="mt-1.5 space-y-1">
                  {hypotheses.map((h) => (
                    <li key={h.id} className="flex items-center justify-between gap-3">
                      <span>
                        {h.id} · {h.title}
                      </span>
                      <span className="font-mono font-semibold">{h.confidence}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {gaps && (
              <div className="rounded-lg border border-slate-200 p-3.5">
                <p className="font-semibold text-navy-800">Investigation gaps ({gaps.total})</p>
                <ol className="mt-1.5 list-inside list-decimal space-y-0.5">
                  {gaps.items.slice(0, 3).map((g) => (
                    <li key={g.id}>
                      {g.title} — impact {g.impact.toLowerCase()}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <div className="rounded-lg border border-slate-200 p-3.5">
              <p className="font-semibold text-navy-800">Evidence chain (sample)</p>
              <div className="mt-2">
                <EvidenceChain
                  chain={[
                    { key: 'f', label: 'Finding', icon: <span className="text-[11px]">01</span>, title: 'Recorded association' },
                    { key: 'r', label: 'Relationship', icon: <span className="text-[11px]">02</span>, title: 'Link under analyst review' },
                    { key: 'e', label: 'Evidence', icon: <span className="text-[11px]">03</span>, title: `${stats.evidence} records indexed` },
                    { key: 's', label: 'Source File', icon: <span className="text-[11px]">04</span>, title: 'Chain of custody maintained' },
                    { key: 'o', label: 'Original Record', icon: <span className="text-[11px]">05</span>, title: formatDate(new Date()) },
                  ]}
                />
              </div>
            </div>
          </div>

          <p className="mt-6 border-t border-slate-200 pt-3 text-[10.5px] leading-relaxed text-navy-300">
            NEXUS provides analytical assistance and investigation leads. It does not determine guilt or replace investigator
            judgment. Figures in this preview are mock values from the frontend-only build.
          </p>
        </div>
      )}
    </Modal>
  );
}
