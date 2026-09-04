import { useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, FileText, Info, ShieldQuestion, SlidersHorizontal } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Drawer } from '@/components/modals/Drawer';
import { EmptyState } from '@/components/ui/EmptyState';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton, SyntheticNotice } from '@/components/analysis/AnalysisState';
import { DocumentDrawer } from '@/components/analysis/DocumentDrawer';
import { ImpactPanel } from '@/components/analysis/ImpactPanel';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { cnaContradictionType, cnaSeverity, cnaSourceType, formatPercent } from '@/lib/cna';
import { cn } from '@/lib/utils';

/**
 * Contradictions — the engine that argues with the graph.
 *
 * Every number on this screen comes from `backend/app/intelligence`. Nothing
 * is computed in the browser, and nothing is presented as a conclusion: each
 * item shows the rule that fired, both sides of the evidence, and the
 * confidence revision that follows, so an investigator can disagree with the
 * arithmetic rather than with an oracle.
 */
export function ConflictsPage() {
  const [severity, setSeverity] = useState('all');
  const [type, setType] = useState('all');
  const [detail, setDetail] = useState(null);
  const [docId, setDocId] = useState(null);
  const [showSkipped, setShowSkipped] = useState(false);

  const { data, error, loading, reload } = useCnaResource(() => cnaService.getContradictions(), []);

  const items = data?.items || [];
  const filtered = useMemo(
    () =>
      items.filter(
        (c) => (severity === 'all' || c.severity === severity) && (type === 'all' || c.type === type)
      ),
    [items, severity, type]
  );

  const skipped = data?.skipped || [];
  const cfg = data?.config || {};

  if (error && !data) {
    return (
      <Card>
        <AnalysisError error={error} onRetry={reload} />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Contradictions"
          subtitle="Records that cannot comfortably all be true. Each is a lead for verification, not a conclusion — the engine does not decide which record is wrong, and it never changes case data."
        />
        <CardBody className="space-y-4 pt-0">
          {loading && !data ? (
            <AnalysisSkeleton rows={3} />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="neutral">{items.length} detected</Badge>
                {Object.entries(data?.counts_by_severity || {}).map(([sev, n]) =>
                  n > 0 ? (
                    <Badge key={sev} variant={cnaSeverity(sev).variant} dot>
                      {cnaSeverity(sev).label} {n}
                    </Badge>
                  ) : null
                )}
                {skipped.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowSkipped((v) => !v)}
                    className="ml-auto text-[12px] font-medium text-teal-700 hover:text-teal-800"
                  >
                    {showSkipped ? 'Hide' : 'Show'} {skipped.length} pair(s) examined and not flagged
                  </button>
                )}
              </div>

              {/* Thresholds are part of the finding: a rule the reader cannot see is not reviewable. */}
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl border border-slate-200 p-3 text-[11.5px] text-navy-400">
                <span className="flex items-center gap-1.5 font-semibold uppercase tracking-[0.1em] text-navy-300">
                  <SlidersHorizontal className="h-3 w-3" aria-hidden /> Thresholds
                </span>
                <span>
                  Impossible above <strong className="font-semibold text-navy-600">{cfg.max_reasonable_speed_kmph} km/h</strong>
                </span>
                <span>
                  Unusual above <strong className="font-semibold text-navy-600">{cfg.unusual_speed_kmph} km/h</strong>
                </span>
                <span>
                  Same locality under <strong className="font-semibold text-navy-600">{cfg.min_separation_km} km</strong>
                </span>
                <span>
                  Vehicle window <strong className="font-semibold text-navy-600">{cfg.vehicle_window_hours} h</strong>
                </span>
                <span>
                  Stated-time slack <strong className="font-semibold text-navy-600">±{cfg.stated_time_tolerance_minutes} min</strong>
                </span>
                <span>
                  Max confidence impact <strong className="font-semibold text-navy-600">{formatPercent(cfg.confidence_impact_cap)}</strong>
                </span>
              </div>

              {showSkipped && (
                <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy-300">
                    Examined and not flagged
                  </p>
                  <p className="mt-1 text-[12px] leading-relaxed text-navy-400">
                    Where the engine declined to draw a conclusion. Most are records that fix only a
                    calendar date, which cannot support a conflict measured in minutes.
                  </p>
                  <ul className="mt-2.5 max-h-52 space-y-1.5 overflow-y-auto scrollbar-thin">
                    {skipped.slice(0, 60).map((s, i) => (
                      <li key={i} className="text-[12px] leading-relaxed text-navy-500">
                        <span className="font-mono text-[10px] font-semibold uppercase text-navy-300">
                          {String(s.check).replace(/_/g, ' ')} · {s.reason}
                        </span>{' '}
                        — {s.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy-300">Severity</span>
                {['all', 'high', 'medium', 'low'].map((s) => (
                  <FilterChip key={s} active={severity === s} onClick={() => setSeverity(s)}>
                    {s === 'all' ? `All ${items.length}` : `${cnaSeverity(s).label} ${data?.counts_by_severity?.[s] ?? 0}`}
                  </FilterChip>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy-300">Type</span>
                <FilterChip active={type === 'all'} onClick={() => setType('all')}>
                  All
                </FilterChip>
                {Object.entries(data?.counts_by_type || {}).map(([t, n]) => {
                  const meta = cnaContradictionType(t);
                  return (
                    <FilterChip key={t} active={type === t} onClick={() => setType(t)}>
                      <meta.icon className="h-3 w-3" aria-hidden /> {meta.label} {n}
                    </FilterChip>
                  );
                })}
              </div>
            </>
          )}
        </CardBody>
      </Card>

      {!loading && filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={ShieldQuestion}
            title="No contradictions for this filter"
            description="The engine found no conflicting records matching the selected severity and type."
          />
        </Card>
      ) : (
        filtered.map((c) => (
          <ContradictionCard key={c.id} c={c} onEvidence={setDetail} onDocument={setDocId} />
        ))
      )}

      <SyntheticNotice />
      <AnalysisDisclosure />

      <EvidenceDrawer contradiction={detail} onClose={() => setDetail(null)} onDocument={setDocId} />
      <DocumentDrawer docId={docId} open={Boolean(docId)} onClose={() => setDocId(null)} />
    </div>
  );
}

function FilterChip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-medium ring-1 ring-inset transition-colors',
        active
          ? 'bg-navy-900 text-white ring-navy-900'
          : 'text-navy-500 ring-slate-300 hover:text-navy-800'
      )}
    >
      {children}
    </button>
  );
}

/** One contradiction: what fired, both sides, and the revision it implies. */
function ContradictionCard({ c, onEvidence, onDocument }) {
  const meta = cnaContradictionType(c.type);
  const sev = cnaSeverity(c.severity);
  const a = c.assessment || {};
  const before = Math.round((a.confidence_before || 0) * 100);
  const after = Math.round((a.confidence_after || 0) * 100);

  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
              <meta.icon className="h-3.5 w-3.5" aria-hidden />
            </span>
            <div>
              <p className="text-[14px] font-semibold leading-snug text-navy-900">{c.title}</p>
              <p className="mt-0.5 text-[11px] font-medium uppercase tracking-[0.1em] text-navy-300">
                {meta.label} · {c.id}
              </p>
            </div>
          </div>
          <Badge variant={sev.variant} dot>
            {sev.label}
          </Badge>
        </div>

        <p className="text-[13px] leading-relaxed text-navy-500">{c.description}</p>

        {meta.question && (
          <p className="flex items-start gap-1.5 text-[12px] italic leading-relaxed text-navy-400">
            <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            {meta.question}
          </p>
        )}

        {/* The rule that fired, with its numbers. */}
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Rule that fired</p>
          <p className="mt-1 font-mono text-[12px] text-navy-700">{c.basis?.rule}</p>
          <dl className="mt-2 grid grid-cols-2 gap-x-5 gap-y-1 sm:grid-cols-3">
            {Object.entries(c.basis || {})
              .filter(([k, v]) => k !== 'rule' && v !== null && v !== undefined && typeof v !== 'object')
              .map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-2 border-b border-slate-100 py-0.5">
                  <dt className="text-[10.5px] uppercase tracking-[0.08em] text-navy-300">{k.replace(/_/g, ' ')}</dt>
                  <dd className="font-mono text-[12px] font-semibold text-navy-700">{String(v)}</dd>
                </div>
              ))}
          </dl>
        </div>

        {/* Both sides. */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <EvidenceColumn
            tone="support"
            title={`Supporting evidence (${c.supporting_evidence?.length || 0})`}
            rows={c.supporting_evidence || []}
            onDocument={onDocument}
          />
          <EvidenceColumn
            tone="contra"
            title={`Contradicting evidence (${c.contradicting_evidence?.length || 0})`}
            rows={c.contradicting_evidence || []}
            onDocument={onDocument}
          />
        </div>

        {/* Impact. */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-slate-200 p-3">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-navy-300">
            Relationship confidence
          </span>
          <span className="font-mono text-[13px] text-navy-500">
            {before}% <ArrowRight className="inline h-3 w-3" aria-hidden />{' '}
            <span className="font-semibold text-amber-700">{after}%</span>
          </span>
          <div className="h-1.5 min-w-[100px] flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-amber-500" style={{ width: `${after}%` }} />
          </div>
          <Button variant="outline" size="sm" icon={AlertTriangle} onClick={() => onEvidence(c)}>
            View evidence
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function EvidenceColumn({ tone, title, rows, onDocument }) {
  const support = tone === 'support';
  return (
    <div
      className={cn(
        'rounded-xl border p-3',
        support ? 'border-emerald-100 bg-emerald-50/40' : 'border-amber-100 bg-amber-50/40'
      )}
    >
      <p className={cn('text-[11px] font-semibold', support ? 'text-emerald-700' : 'text-amber-700')}>{title}</p>
      <ul className="mt-2 space-y-1.5">
        {rows.length === 0 && <li className="text-[12px] text-navy-300">None recorded.</li>}
        {rows.slice(0, 6).map((r, i) => {
          const src = cnaSourceType(r.source_type);
          return (
            <li key={`${r.source_id}-${r.record_id || i}`}>
              <button
                type="button"
                onClick={() => onDocument(r.source_id)}
                className="group flex w-full items-start gap-1.5 text-left text-[12.5px] text-navy-600 hover:text-navy-900"
                title="Open the source record"
              >
                {support ? (
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden />
                ) : (
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
                )}
                <span className="min-w-0">
                  <span className="rounded bg-white px-1 font-mono text-[10px] font-semibold text-navy-500 ring-1 ring-slate-200">
                    {r.source_id}
                    {r.record_id ? ` · ${r.record_id}` : ''}
                  </span>
                  <span className="ml-1.5 text-[10.5px] uppercase tracking-[0.08em] text-navy-300">{src.label}</span>
                  <span className="mt-0.5 block leading-relaxed text-navy-500 group-hover:text-navy-700">{r.detail}</span>
                </span>
              </button>
            </li>
          );
        })}
        {rows.length > 6 && (
          <li className="text-[11.5px] text-navy-300">+{rows.length - 6} more in the evidence drawer</li>
        )}
      </ul>
    </div>
  );
}

/** Full provenance, the scoring working, and what to do about it. */
function EvidenceDrawer({ contradiction, onClose, onDocument }) {
  const c = contradiction;
  const a = c?.assessment || {};
  return (
    <Drawer
      open={Boolean(c)}
      onClose={onClose}
      width={620}
      title="Why this was flagged"
      subtitle={c ? `${c.id} · ${cnaContradictionType(c.type).label}` : ''}
    >
      {c && (
        <div className="space-y-5">
          <p className="text-[13px] leading-relaxed text-navy-600">{c.description}</p>

          {/* Events, in order. */}
          {c.events?.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
                Records in conflict
              </h4>
              <ol className="mt-2 space-y-2">
                {c.events.map((e, i) => (
                  <li key={i} className="rounded-lg border border-slate-200 p-2.5">
                    <p className="font-mono text-[11px] font-semibold text-navy-700">
                      {e.timestamp ? `${e.timestamp.replace('T', ' ').slice(0, 16)} · ` : ''}
                      {e.place || e.asset || e.attribute}
                      {e.value ? ` = ${e.value}` : ''}
                      {e.entity_label ? ` · ${e.entity_label}` : ''}
                      {e.claimed_owner ? ` · ${e.claimed_owner}` : ''}
                    </p>
                    <p className="mt-0.5 text-[11.5px] text-navy-400">
                      {cnaSourceType(e.source_type).label} · {e.source_id}
                      {e.time_precision ? ` · time precision: ${e.time_precision}` : ''}
                    </p>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Scoring, shown as arithmetic rather than a verdict. */}
          <section>
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
              How the confidence was revised
            </h4>
            <dl className="mt-2 space-y-1 rounded-lg border border-slate-200 p-3">
              <Row k="Support score" v={a.support_score} />
              <Row k="Contradiction score" v={a.contradiction_score} />
              <Row k="Contradiction ratio" v={a.contradiction_ratio} />
              <Row k="Confidence before" v={a.confidence_before} />
              <Row k="Confidence after" v={a.confidence_after} />
            </dl>
            <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-navy-400">{a.formula}</p>
            <p className="mt-2 text-[11.5px] leading-relaxed text-navy-400">
              This is an evidence-supported relationship confidence. It is not a probability that any
              person did anything.
            </p>
          </section>

          {/* Per-record weights. */}
          {a.terms?.contradicting?.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
                Weight of each contradicting record
              </h4>
              <table className="mt-2 w-full text-left text-[11.5px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-[0.08em] text-navy-300">
                    <th className="py-1 font-medium">Source</th>
                    <th className="py-1 font-medium">Reliability</th>
                    <th className="py-1 font-medium">Confidence</th>
                    <th className="py-1 text-right font-medium">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {a.terms.contradicting.map((t, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="py-1 font-mono text-navy-600">{t.source_type}</td>
                      <td className="py-1 font-mono text-navy-500">{t.reliability}</td>
                      <td className="py-1 font-mono text-navy-500">{t.record_confidence}</td>
                      <td className="py-1 text-right font-mono font-semibold text-navy-700">{t.weight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {c.possible_explanations?.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
                Possible explanations
              </h4>
              <p className="mt-1 text-[11.5px] text-navy-400">
                Listed, not ranked. The engine does not choose between them.
              </p>
              <ul className="mt-2 space-y-1.5">
                {c.possible_explanations.map((e, i) => (
                  <li key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-navy-600">
                    <span className="text-navy-300">•</span>
                    {e}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {c.recommended_verification?.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
                Recommended verification
              </h4>
              <ul className="mt-2 space-y-1.5">
                {c.recommended_verification.map((e, i) => (
                  <li key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-navy-600">
                    <span className="text-navy-300">{i + 1}.</span>
                    {e}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* The contradiction's own provenance seeds the simulator: the records
              that produced the conflict are exactly the ones worth withholding. */}
          <section>
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
              If this evidence were withheld
            </h4>
            <div className="mt-2">
              <ImpactPanel
                key={c.id}
                sources={[...new Set((c.contradicting_evidence || [])
                  .filter((r) => !r.record_id)
                  .map((r) => r.source_id))]}
                records={[...new Set((c.contradicting_evidence || [])
                  .filter((r) => r.record_id)
                  .map((r) => r.record_id))]}
                label="the records behind this contradiction"
              />
            </div>
          </section>

          <section>
            <h4 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Source records</h4>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {[...new Set([...(c.supporting_evidence || []), ...(c.contradicting_evidence || [])].map((r) => r.source_id))].map(
                (sid) => (
                  <button
                    key={sid}
                    type="button"
                    onClick={() => onDocument(sid)}
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-mono text-[11px] text-navy-600 ring-1 ring-inset ring-slate-300 hover:text-navy-900"
                  >
                    <FileText className="h-3 w-3" aria-hidden />
                    {sid}
                  </button>
                )
              )}
            </div>
          </section>
        </div>
      )}
    </Drawer>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-[11.5px] text-navy-400">{k}</dt>
      <dd className="font-mono text-[12px] font-semibold text-navy-700">{v ?? '—'}</dd>
    </div>
  );
}
