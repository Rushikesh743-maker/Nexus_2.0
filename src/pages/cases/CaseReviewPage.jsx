import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  UserPlus,
  GitMerge,
  ArrowLeftRight,
  FileCheck2,
  AlertTriangle,
  Check,
  X,
  Minus,
  Play,
  Loader2,
  ClipboardCheck,
} from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useToast } from '@/context/ToastContext';
import { useCnaResource } from '@/hooks/useCnaResource';
import { analysisService, documentService, V1Error } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { cn, formatDateTime } from '@/lib/utils';

/**
 * Case-level review queue — the five sections of work waiting on a human
 * decision in this ONE case:
 *   1. New entities            3. Candidate relationships
 *   2. Potential duplicates    4. Evidence claims
 *   5. Potential contradictions
 *
 * Nothing here is auto-confirmed: matches are suggestions with the exact
 * signals that fired, relationships only exist when the text/columns state
 * them, and the engine never decides a contradiction — it flags the pair
 * and the investigator does. Every row carries its source document so a
 * decision is always made against the record, not against a summary.
 */

function Section({ title, icon: Icon, count, children, empty }) {
  return (
    <Card>
      <CardHeader
        title={title}
        actions={
          <Badge variant={count > 0 ? 'warning' : 'default'}>{count} pending</Badge>
        }
      />
      {children ?? <EmptyState compact icon={Icon} title={empty} />}
    </Card>
  );
}

function Confidence({ value }) {
  if (typeof value !== 'number') return null;
  return (
    <span className="figure text-[10.5px] text-navy-400">
      {(value * 100).toFixed(0)}% confidence
    </span>
  );
}

function RowActions({ busy, onConfirm, onReject, onDefer, confirmLabel = 'Confirm', rejectLabel = 'Reject' }) {
  return (
    <div className="flex items-center gap-1.5">
      <Button size="sm" variant="primary" loading={busy === 'accept'} icon={Check} onClick={onConfirm}>
        {confirmLabel}
      </Button>
      <Button size="sm" variant="outline" loading={busy === 'reject'} icon={X} onClick={onReject}>
        {rejectLabel}
      </Button>
      {onDefer && (
        <Button size="sm" variant="ghost" icon={Minus} onClick={onDefer} title="Defer">
          Defer
        </Button>
      )}
    </div>
  );
}

export function CaseReviewPage() {
  const { caseFile: c } = useCaseFile();
  const toast = useToast();
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(null);
  const [running, setRunning] = useState(false);

  const { data: q, error, loading, reload } = useCnaResource(
    useCallback(() => analysisService.getReviewQueue(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );

  const bump = () => setReloadKey((k) => k + 1);

  const act = async (label, fn) => {
    setBusy(label);
    try {
      await fn();
      reload();
    } catch (err) {
      toast.error(err.message || 'Action failed.');
      if (err instanceof V1Error && err.status === 409) reload();
    } finally {
      setBusy(null);
    }
  };

  const runIntelligence = async () => {
    setRunning(true);
    try {
      const res = await analysisService.runCaseAnalysis(c.id);
      if (res.status === 'completed') {
        toast.success(`Analysis complete — ${res.findings_count} finding(s), ${res.hypotheses_count} hypothesis(es).`);
      } else {
        toast.info(res.reason || res.status);
      }
      reload();
    } catch (err) {
      toast.error(err.message || 'Analysis run failed.');
    } finally {
      setRunning(false);
    }
  };

  if (loading && !q) return <PageLoader label="Loading review queue…" />;
  if (error && !q) return <ErrorState title="Review queue unavailable" description={error.message} onRetry={reload} />;

  const emptyQueue = q && q.total_pending === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-display text-[17px] text-navy-900">Review queue</h2>
          <p className="text-[12px] text-navy-400">
            {q?.total_pending ?? 0} decision(s) waiting in this case — every row is tied to its source document.
          </p>
        </div>
        {emptyQueue && (
          <Button icon={running ? Loader2 : Play} loading={running} onClick={runIntelligence}>
            Run intelligence
          </Button>
        )}
      </div>

      {emptyQueue && (
        <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3">
          <ClipboardCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
          <p className="text-[12.5px] text-emerald-800">
            The review queue is empty. Run the intelligence now — it analyzes exactly the confirmed
            data in this case, and its findings appear on the Intelligence and Reports tabs.
          </p>
        </div>
      )}

      <Section
        title="New entities"
        icon={UserPlus}
        count={q?.new_entities?.length ?? 0}
        empty="No new entities waiting"
      >
        <ul className="divide-y divide-line-soft">
          {(q?.new_entities || []).map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-navy-800">
                  {e.name}
                  <span className="ml-2 text-[10.5px] font-normal uppercase tracking-wide text-navy-400">{e.entity_type}</span>
                </p>
                <p className="mt-0.5 text-[11px] text-navy-400">
                  from <span className="font-medium text-navy-600">{e.source_document}</span>
                  {e.source_snippet && <> · “{e.source_snippet}”</>}
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <Confidence value={e.confidence} />
                  <span className="figure text-[10px] text-navy-300">{e.extraction_method}</span>
                </div>
              </div>
              <RowActions
                busy={busy}
                onConfirm={() => act(`e${e.id}`, () => documentService.acceptCandidate(e.document_id, e.id))}
                onReject={() => act(`e${e.id}`, () => documentService.rejectCandidate(e.document_id, e.id))}
                onDefer={() => act(`e${e.id}`, () => documentService.deferCandidate(e.document_id, e.id))}
              />
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Potential duplicate entities"
        icon={GitMerge}
        count={q?.potential_duplicates?.length ?? 0}
        empty="No duplicate suggestions"
      >
        {/* Phase 2: ranked suggestions — every candidate can carry several,
            best first, each with the exact signals that fired. Accepting
            one ranks the rest of the same candidate as superseded. */}
        <ul className="divide-y divide-line-soft">
          {(q?.potential_duplicates || []).map((m, idx, all) => {
            const total = m.suggestions_total ?? 1;
            const rank = m.rank ?? (idx + 1);
            const firstOfCandidate = !all[idx - 1] || all[idx - 1].id !== m.id;
            return (
              <li key={`${m.id}-${m.match_id}`} className={cn('flex flex-wrap items-center justify-between gap-3 px-4 py-3', !firstOfCandidate && 'border-l-2 border-l-line pl-6')}>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-navy-800">
                    {firstOfCandidate ? m.name : <span className="text-navy-400">{m.name}</span>}
                    <span className="figure mx-2 text-[12px] text-navy-400">≈ {((m.similarity ?? 0) * 100).toFixed(0)}%</span>
                    {m.existing_entity_name}
                    {total > 1 && (
                      rank === 1
                        ? <Badge variant="teal" className="ml-2">Best match · 1 of {total}</Badge>
                        : <Badge variant="neutral" className="ml-2">Suggestion {rank} of {total}</Badge>
                    )}
                  </p>
                  <p className="mt-0.5 text-[11px] text-navy-400">
                    {m.existing_entity_name} is already confirmed in this case
                    {m.source_document && <> · candidate from {m.source_document}</>}
                  </p>
                  <ul className="mt-1.5 space-y-0.5">
                    {(m.match_reasons || []).map((r, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-[11px] text-navy-500">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-navy-300" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
                <RowActions
                  busy={busy}
                  confirmLabel="Confirm match"
                  onConfirm={() => act(`m${m.match_id}`, () => documentService.acceptMatch(m.document_id, m.match_id))}
                  onReject={() => act(`m${m.match_id}`, () => documentService.rejectMatch(m.document_id, m.match_id))}
                />
              </li>
            );
          })}
        </ul>
      </Section>

      <Section
        title="Candidate relationships"
        icon={ArrowLeftRight}
        count={q?.candidate_relationships?.length ?? 0}
        empty="No relationship candidates"
      >
        <ul className="divide-y divide-line-soft">
          {(q?.candidate_relationships || []).map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[13px] text-navy-800">
                  <span className="font-medium">{r.source_name}</span>
                  <span className="figure mx-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-navy-500">{r.relationship_type}</span>
                  <span className="font-medium">{r.target_name}</span>
                </p>
                <p className="mt-0.5 text-[11px] text-navy-400">
                  from <span className="font-medium text-navy-600">{r.source_document}</span>
                  {r.source_snippet && <> · “{r.source_snippet}”</>}
                </p>
                <div className="mt-1">
                  <Confidence value={r.confidence} />
                </div>
              </div>
              <RowActions
                busy={busy}
                confirmLabel="Confirm"
                onConfirm={() => act(`r${r.id}`, () => documentService.acceptRelationship(r.document_id, r.id))}
                onReject={() => act(`r${r.id}`, () => documentService.rejectRelationship(r.document_id, r.id))}
              />
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Evidence claims"
        icon={FileCheck2}
        count={0}
        empty="No structured claims yet"
      >
        {(q?.evidence_claims || []).length > 0 && (
          <ul className="divide-y divide-line-soft">
            {q.evidence_claims.map((cl) => (
              <li key={cl.id} className="px-4 py-3">
                <p className="text-[13px] text-navy-800">
                  <span className="font-medium">{cl.subject}</span>
                  <span className="figure mx-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-navy-500">{cl.predicate}</span>
                  <span className="font-medium">{cl.object}</span>
                </p>
                <p className="mt-0.5 text-[11px] text-navy-400">
                  {cl.event_time ? `${formatDateTime(cl.event_time)} · ` : ''}
                  {cl.source_document && <span>{cl.source_document}</span>}
                  {cl.evidence_type && <span className="figure text-navy-300"> · {cl.evidence_type}</span>}
                </p>
              </li>
            ))}
          </ul>
        )}
        {(q?.evidence_claims || []).length === 0 && (
          <EmptyState compact icon={FileCheck2} title="No structured claims yet" description="Confirmed was_at / present_at claims from documents appear here." />
        )}
      </Section>

      <Section
        title="Potential contradictions"
        icon={AlertTriangle}
        count={(q?.potential_contradictions || []).filter((f) => f.is_current).length}
        empty="No contradiction findings"
      >
        <ul className="divide-y divide-line-soft">
          {(q?.potential_contradictions || []).map((f) => (
            <li key={f.id} className="px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[13px] font-medium text-navy-800">{f.title}</p>
                <div className="flex items-center gap-1.5">
                  {f.severity && <Badge variant={f.severity === 'HIGH' ? 'danger' : 'warning'}>{f.severity}</Badge>}
                  {!f.is_current && <Badge variant="default">stale snapshot</Badge>}
                  <Link to={`/cases/${c.id}/contradictions`} className="text-[11.5px] font-medium text-navy-500 hover:text-navy-900">
                    Details →
                  </Link>
                </div>
              </div>
              {f.explanation && (
                <ul className="mt-1.5 space-y-0.5">
                  {f.explanation.slice(0, 3).map((line, i) => (
                    <li key={i} className="text-[11px] text-navy-500">{line}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
