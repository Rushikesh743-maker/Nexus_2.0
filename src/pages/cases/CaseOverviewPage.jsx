import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Network,
  FileText,
  MapPin,
  Clock,
  Lightbulb,
  AlertTriangle,
  HelpCircle,
  GitCompareArrows,
  Play,
  Loader2,
  CheckCircle2,
  Circle,
  AlertCircle,
} from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { StatCard } from '@/components/cards/StatCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/context/ToastContext';
import { useCnaResource } from '@/hooks/useCnaResource';
import { analysisService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';
import { EntityChip } from '@/components/cases/EntityChip';

const ENTITY_TYPE_LABEL = {
  person: 'Person',
  organization: 'Organization',
  vehicle: 'Vehicle',
  location: 'Location',
  phone: 'Phone',
  account: 'Account',
  case_reference: 'Case ref',
  other: 'Other',
};

const STATE_LABEL = {
  'not-analyzed': 'Intelligence not run yet',
  'up-to-date': 'Intelligence up to date',
  stale: 'Intelligence stale — data changed',
  insufficient: 'Not enough confirmed data to analyze',
};

/**
 * Case overview — the central investigation workspace.
 *
 * Everything on this page comes from the live case: headline counts from
 * the case payload, and the pipeline state (documents, pending review,
 * analysis freshness) from the real analysis-status endpoint. The
 * "Case readiness" panel states exactly what the next action is — no
 * invented progress, no fake percentages.
 */
export function CaseOverviewPage() {
  const { caseFile: c } = useCaseFile();
  const toast = useToast();
  const counts = c.counts || {};
  const [running, setRunning] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const { data: status } = useCnaResource(
    () => analysisService.getAnalysisStatus(c.id),
    [c.id, reloadKey]
  );

  const runIntelligence = async () => {
    setRunning(true);
    try {
      const res = await analysisService.runCaseAnalysis(c.id);
      if (res.status === 'completed') {
        toast.success(`Analysis complete — ${res.findings_count} finding(s).`);
      } else {
        toast.info(res.reason || res.status);
      }
      setReloadKey((k) => k + 1);
    } catch (err) {
      toast.error(err.message || 'Analysis run failed.');
    } finally {
      setRunning(false);
    }
  };

  const recentEvents = useMemo(
    () => (c.latest_events || []).slice(0, 6).reverse(),
    [c]
  );

  // deterministic next action (the guided workflow)
  const readiness = useMemo(() => {
    const docs = counts.documents ?? 0;
    const pending = status?.pending_review
      ? (status.pending_review.entity_candidates + status.pending_review.entity_matches
         + status.pending_review.relationship_candidates)
      : null;
    const processed = status?.documents?.all_processed;
    const state = status?.state;
    const steps = [
      {
        label: 'Documents',
        state: docs > 0 ? (processed ? 'done' : 'active') : 'todo',
        detail: docs > 0 ? `${docs} uploaded` : 'none yet',
      },
      {
        label: 'Extraction',
        state: docs > 0 ? (processed ? 'done' : 'active') : 'todo',
        detail: processed ? 'complete' : docs > 0 ? 'in progress' : 'waiting for documents',
      },
      {
        label: 'Review',
        state: pending == null ? 'todo' : pending === 0 ? (docs > 0 ? 'done' : 'todo') : 'warn',
        detail: pending == null ? '—' : pending === 0 ? 'queue empty' : `${pending} candidate(s) pending`,
      },
      {
        label: 'Graph',
        state: (counts.entities ?? 0) > 0 ? 'done' : 'todo',
        detail: `${counts.entities ?? 0} entities · ${counts.relationships ?? 0} relationships`,
      },
      {
        label: 'Intelligence',
        state: state === 'up-to-date' ? 'done'
          : state === 'stale' ? 'warn'
          : state === 'insufficient' ? 'warn'
          : docs > 0 ? 'todo' : 'todo',
        detail: STATE_LABEL[state] || 'not run',
      },
    ];
    let next;
    if (docs === 0) next = { label: 'Upload your first document', to: `/cases/${c.id}/documents`, run: false };
    else if (!processed) next = { label: 'Wait for processing to finish', to: `/cases/${c.id}/documents`, run: false };
    else if (pending > 0) next = { label: `Review ${pending} candidate(s)`, to: `/cases/${c.id}/review`, run: false };
    else if (state === 'insufficient') next = { label: 'Confirm more candidates to enable analysis', to: `/cases/${c.id}/review`, run: false };
    else if (state === 'stale') next = { label: 'Re-run intelligence', to: null, run: true };
    else if (state === 'not-analyzed') next = { label: 'Run intelligence', to: null, run: true };
    else next = { label: 'Explore the findings', to: `/cases/${c.id}/investigation`, run: false };
    return { steps, next };
  }, [counts, status, c.id]);

  return (
    <div className="space-y-5">
      {/* pipeline state strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-line bg-slate-50/70 px-4 py-2.5">
        <span className="text-[12px] font-medium text-navy-700">
          {STATE_LABEL[status?.state] || 'Loading pipeline state…'}
        </span>
        {status?.graph_version && (
          <span className="figure text-[10.5px] text-navy-400">snapshot {status.graph_version}</span>
        )}
        {status?.documents?.total != null && (
          <span className="text-[10.5px] text-navy-400">
            {status.documents.total} document(s)
            {Object.entries(status.documents.by_status || {}).map(([k, v]) => (
              <span key={k}> · {v} {k}</span>
            ))}
          </span>
        )}
        {status?.findings && (
          <span className="text-[10.5px] text-navy-400">
            {status.findings.current} current finding(s)
            {status.findings.stale > 0 && ` · ${status.findings.stale} stale`}
          </span>
        )}
        {(status?.state === 'stale' || status?.state === 'not-analyzed') && counts.entities > 0 && (
          <Button size="sm" icon={running ? Loader2 : Play} loading={running} onClick={runIntelligence} className="ml-auto">
            {status?.state === 'stale' ? 'Re-run intelligence' : 'Run intelligence'}
          </Button>
        )}
      </div>

      {/* Headline counts — straight from the case payload. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Entities" value={counts.entities ?? 0} sub="persons, vehicles, places" to={`/cases/${c.id}/entities`} />
        <StatCard label="Relationships" value={counts.relationships ?? 0} sub="typed links between entities" to={`/cases/${c.id}/relationships`} />
        <StatCard label="Evidence items" value={counts.evidence ?? 0} sub="records tied to documents" to={`/cases/${c.id}/evidence`} />
        <StatCard label="Findings" value={status?.findings?.current ?? 0} sub={`${counts.contradictions ?? 0} contradictions · ${counts.hypotheses ?? 0} hypotheses`} to={`/cases/${c.id}/investigation`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* case readiness — the guided workflow */}
        <Card>
          <CardHeader
            title="Case readiness"
            subtitle="Where this case stands in the workflow — and the next action"
          />
          <ul className="divide-y divide-line-soft">
            {readiness.steps.map((s) => (
              <li key={s.label} className="flex items-center gap-3 px-4 py-2.5">
                {s.state === 'done' && <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />}
                {s.state === 'active' && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-sky-600" aria-hidden />}
                {s.state === 'warn' && <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" aria-hidden />}
                {s.state === 'todo' && <Circle className="h-4 w-4 shrink-0 text-navy-200" aria-hidden />}
                <span className="text-[12.5px] font-medium text-navy-800">{s.label}</span>
                <span className="ml-auto text-[11px] text-navy-400">{s.detail}</span>
              </li>
            ))}
          </ul>
          <div className="border-t border-line bg-slate-50/60 px-4 py-3">
            <p className="label-micro mb-1.5">Next action</p>
            {readiness.next.run ? (
              <Button icon={running ? Loader2 : Play} loading={running} onClick={runIntelligence}>
                {readiness.next.label}
              </Button>
            ) : (
              <Link to={readiness.next.to}>
                <Button>{readiness.next.label}</Button>
              </Link>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Key entities"
            subtitle={`${counts.entities ?? 0} in this case`}
            actions={
              <Link to={`/cases/${c.id}/graph`} className="text-[12px] font-medium text-navy-500 hover:text-navy-900">
                Open graph →
              </Link>
            }
          />
          {c.key_entities?.length ? (
            <ul className="grid grid-cols-1 gap-2 p-4 pt-2 sm:grid-cols-2">
              {c.key_entities.map((e) => (
                <EntityChip key={e.id} entity={e} typeLabel={ENTITY_TYPE_LABEL[e.type] || e.type} />
              ))}
            </ul>
          ) : (
            <EmptyState compact icon={Network} title="No entities yet" description="Entities extracted or recorded into this case will appear here." />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Recent activity"
            subtitle="Latest timeline events"
            actions={
              <Link to={`/cases/${c.id}/timeline`} className="text-[12px] font-medium text-navy-500 hover:text-navy-900">
                Full timeline →
              </Link>
            }
          />
          {recentEvents.length ? (
            <ul className="divide-y divide-line-soft">
              {recentEvents.map((ev) => (
                <li key={ev.id} className="flex items-start gap-3 px-4 py-2.5">
                  <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                  <div className="min-w-0">
                    <p className="truncate text-[12.5px] text-navy-800">{ev.description}</p>
                    <p className="text-[11px] text-navy-400">
                      <span className="figure">{ev.event_type}</span> · {formatDateTime(ev.timestamp)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact icon={Clock} title="No events yet" description="Dated occurrences recorded into the case will appear here." />
          )}
        </Card>

        <Card>
          <CardHeader title="Working state" subtitle="Hypotheses, contradictions, gaps and open review" />
          <div className="grid grid-cols-4 divide-x divide-line-soft">
            <Link to={`/cases/${c.id}/hypotheses`} className="group px-3 py-4 text-center transition-colors hover:bg-slate-50">
              <Lightbulb className="mx-auto h-4 w-4 text-navy-300 group-hover:text-navy-600" aria-hidden />
              <p className="figure mt-2 text-[20px] text-navy-900">{counts.hypotheses ?? 0}</p>
              <p className="text-[10.5px] text-navy-400">Hypotheses</p>
            </Link>
            <Link to={`/cases/${c.id}/contradictions`} className="group px-3 py-4 text-center transition-colors hover:bg-slate-50">
              <AlertTriangle className="mx-auto h-4 w-4 text-navy-300 group-hover:text-navy-600" aria-hidden />
              <p className="figure mt-2 text-[20px] text-navy-900">{counts.contradictions ?? 0}</p>
              <p className="text-[10.5px] text-navy-400">Contradictions</p>
            </Link>
            <Link to={`/cases/${c.id}/gaps`} className="group px-3 py-4 text-center transition-colors hover:bg-slate-50">
              <HelpCircle className="mx-auto h-4 w-4 text-navy-300 group-hover:text-navy-600" aria-hidden />
              <p className="figure mt-2 text-[20px] text-navy-900">{counts.gaps ?? 0}</p>
              <p className="text-[10.5px] text-navy-400">Open gaps</p>
            </Link>
            <Link to={`/cases/${c.id}/review`} className="group px-3 py-4 text-center transition-colors hover:bg-slate-50">
              <Badge variant={(status?.pending_review
                ? (status.pending_review.entity_candidates + status.pending_review.entity_matches + status.pending_review.relationship_candidates) > 0
                : false) ? 'warning' : 'default'}>
                <span className="figure text-[14px]">{status?.pending_review
                  ? status.pending_review.entity_candidates + status.pending_review.entity_matches + status.pending_review.relationship_candidates
                  : 0}</span>
              </Badge>
              <p className="text-[10.5px] text-navy-400">Pending review</p>
            </Link>
          </div>
          <div className="grid grid-cols-3 divide-x divide-line-soft border-t border-line-soft">
            <Link to={`/cases/${c.id}/documents`} className="group px-4 py-3 text-center transition-colors hover:bg-slate-50">
              <FileText className="mx-auto h-3.5 w-3.5 text-navy-300 group-hover:text-navy-600" aria-hidden />
              <p className="figure mt-1.5 text-[16px] text-navy-800">{counts.documents ?? 0}</p>
              <p className="text-[10.5px] text-navy-400">Documents</p>
            </Link>
            <Link to={`/cases/${c.id}/map`} className="group px-4 py-3 text-center transition-colors hover:bg-slate-50">
              <MapPin className="mx-auto h-3.5 w-3.5 text-navy-300 group-hover:text-navy-600" aria-hidden />
              <p className="figure mt-1.5 text-[16px] text-navy-800">{counts.locations ?? 0}</p>
              <p className="text-[10.5px] text-navy-400">Locations</p>
            </Link>
            <Link to={`/cases/${c.id}/timeline`} className="group px-4 py-3 text-center transition-colors hover:bg-slate-50">
              <Clock className="mx-auto h-3.5 w-3.5 text-navy-300 group-hover:text-navy-600" aria-hidden />
              <p className="figure mt-1.5 text-[16px] text-navy-800">{counts.timeline_events ?? 0}</p>
              <p className="text-[10.5px] text-navy-400">Events</p>
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
