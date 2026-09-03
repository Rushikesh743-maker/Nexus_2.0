import { useState } from 'react';
import { FileDown, Sparkles, Link2, ShieldAlert, IdCard } from 'lucide-react';
import { Drawer } from '@/components/modals/Drawer';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Tabs } from '@/components/ui/Tabs';
import { AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { EvidenceTrail } from '@/components/analysis/EvidenceTrail';
import { MarkdownReport } from '@/components/analysis/MarkdownReport';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { cnaService } from '@/services';
import { cnaEdgeLabel, cnaNodeType, cnaSeverity, cnaSourceType, formatScore } from '@/lib/cna';
import { formatDate } from '@/lib/utils';

const TABS = [
  { id: 'profile', label: 'Profile', icon: IdCard },
  { id: 'links', label: 'Links', icon: Link2 },
  { id: 'findings', label: 'Findings', icon: ShieldAlert },
];

/**
 * Full subject profile from `/api/entity/{id}`: the generated narrative, every
 * link with the evidence string behind it, and the findings that name this
 * subject. Opening this drawer writes a VIEW_ENTITY entry to the audit log.
 */
export function SubjectDrawer({ nodeId, open, onClose }) {
  const toast = useToast();
  const [tab, setTab] = useState('profile');
  const [exporting, setExporting] = useState(false);
  const [trail, setTrail] = useState(null);

  const { data, error, loading, reload } = useCnaResource(
    () => cnaService.getEntity(nodeId),
    [nodeId],
    { enabled: Boolean(open && nodeId) }
  );

  async function exportPdf() {
    setExporting(true);
    try {
      const { bytes } = await cnaService.downloadEntityPdf(nodeId, data?.label);
      toast.success(`Subject profile exported (${(bytes / 1024).toFixed(0)} KB)`);
    } catch (e) {
      toast.error('Export failed', e.message);
    } finally {
      setExporting(false);
    }
  }

  const meta = cnaNodeType(data?.influence?.type || 'PERSON');

  return (
    <>
      <Drawer
        open={open}
        onClose={onClose}
        title={data?.label || 'Subject profile'}
        subtitle={nodeId}
        width={560}
        footer={
          <Button variant="outline" size="sm" icon={FileDown} loading={exporting} onClick={exportPdf} disabled={!data}>
            Export PDF
          </Button>
        }
      >
        {loading && !data ? (
          <AnalysisSkeleton rows={7} />
        ) : error ? (
          <AnalysisError error={error} onRetry={reload} compact />
        ) : !data ? null : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="neutral">
                <meta.icon className="h-3 w-3" aria-hidden />
                {meta.label}
              </Badge>
              {data.influence && (
                <>
                  <Badge variant="teal">Rank #{data.influence.rank}</Badge>
                  <Badge variant="neutral">Score {formatScore(data.influence.score)}</Badge>
                </>
              )}
              {data.community !== null && data.community !== undefined && (
                <Badge variant="info">Group {data.community}</Badge>
              )}
            </div>

            <Tabs tabs={TABS} value={tab} onChange={setTab} />

            {tab === 'profile' && (
              <div className="space-y-4">
                <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3.5">
                  <div className="mb-2 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-navy-300" aria-hidden />
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">
                      Generated narrative
                    </span>
                    <Badge variant={data.narrative?.machine_drafted ? 'warning' : 'neutral'}>
                      {data.narrative?.machine_drafted ? 'Machine-drafted' : `${data.narrative?.backend || 'template'}`}
                    </Badge>
                  </div>
                  <p className="text-[13px] leading-relaxed text-navy-600">{data.narrative?.text}</p>
                  {data.narrative?.machine_drafted && (
                    <p className="mt-2 text-[11px] leading-relaxed text-amber-700">
                      Drafted by a language model from structured facts only, and rejected if it names anything absent
                      from those facts.
                    </p>
                  )}
                </div>

                <MarkdownReport markdown={data.markdown} />
              </div>
            )}

            {tab === 'links' && (
              <div className="space-y-2.5">
                {(data.links || []).length === 0 ? (
                  <p className="py-6 text-center text-[13px] text-navy-400">No links recorded.</p>
                ) : (
                  data.links.map((link) => {
                    const linkMeta = cnaNodeType(link.type);
                    return (
                      <div key={link.node} className="rounded-lg border border-slate-200 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="flex items-center gap-2 text-[13px] font-medium text-navy-800">
                            <linkMeta.icon className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                            {link.label}
                          </span>
                          <span className="flex items-center gap-1.5">
                            <Badge variant="neutral">conf {formatScore(link.confidence, 2)}</Badge>
                            <Badge variant={link.independent_sources?.length > 1 ? 'success' : 'neutral'}>
                              {link.independent_sources?.length || 0} source
                              {link.independent_sources?.length === 1 ? '' : 's'}
                            </Badge>
                          </span>
                        </div>

                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {(link.relationship || []).map((t) => (
                            <Badge key={t} variant="teal">
                              {cnaEdgeLabel(t)}
                            </Badge>
                          ))}
                        </div>

                        {/* The verbatim evidence strings the backend derived this link from. */}
                        <ul className="mt-2 space-y-1">
                          {(link.evidence || []).map((e, i) => (
                            <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-navy-500">
                              <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-navy-200" aria-hidden />
                              <span>{e}</span>
                            </li>
                          ))}
                        </ul>

                        <div className="mt-2 flex items-center justify-between gap-2">
                          <span className="text-[11px] text-navy-300">
                            {formatDate(link.first_seen)} → {formatDate(link.last_seen)} · {link.observations}{' '}
                            observation{link.observations === 1 ? '' : 's'}
                          </span>
                          <button
                            type="button"
                            onClick={() => setTrail({ a: nodeId, b: link.node })}
                            className="text-[12px] font-medium text-teal-700 hover:text-teal-800"
                          >
                            Why this link?
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {tab === 'findings' && (
              <div className="space-y-2.5">
                {(data.findings || []).length === 0 ? (
                  <p className="py-6 text-center text-[13px] text-navy-400">
                    No suspicious-pattern finding names this subject.
                  </p>
                ) : (
                  data.findings.map((f) => {
                    const sev = cnaSeverity(f.severity);
                    return (
                      <div key={f.id} className="rounded-lg border border-slate-200 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-[13px] font-medium text-navy-800">{f.title}</p>
                          <Badge variant={sev.variant}>{sev.label}</Badge>
                        </div>
                        <p className="mt-1 text-[12px] leading-relaxed text-navy-500">{f.description}</p>
                        {f.basis?.rule && (
                          <p className="mt-1.5 font-mono text-[11px] text-navy-400">Rule: {f.basis.rule}</p>
                        )}
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {(f.sources || []).map((s) => (
                            <Badge key={s} variant="neutral">
                              {cnaSourceType(String(s).toLowerCase()).label}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}
      </Drawer>

      <EvidenceTrail pair={trail} open={Boolean(trail)} onClose={() => setTrail(null)} />
    </>
  );
}
