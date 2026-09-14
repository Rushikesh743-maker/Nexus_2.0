import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUp, Bot, ExternalLink, FileText, GitBranch, Info, Lightbulb,
  ListChecks, MapPin, Network, Search, ShieldCheck, Sparkles, Timer,
  User, X,
} from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { copilotService, V1Error } from '@/services/v1';
import { useCaseFile } from './CaseLayout';

const LANGUAGE_NAMES = { en: 'English', hi: 'Hindi', mr: 'Marathi', ur: 'Urdu' };

const KIND_ICON = {
  entity: User, relationship: GitBranch, evidence: FileText, finding: ListChecks,
  hypothesis: Lightbulb, event: Timer, location: MapPin, claim: ShieldCheck,
  document: FileText,
};

/** Deep links from a citation to the original source record. */
function citationLinks(caseId, cit) {
  const r = cit.record || {};
  switch (cit.kind) {
    case 'evidence':
      return [
        { label: 'View evidence', to: `/cases/${caseId}/evidence?evidence=${cit.id}` },
        ...(r.document_id
          ? [{ label: 'Open document', to: `/cases/${caseId}/documents/${r.document_id}` }]
          : []),
      ];
    case 'claim':
      return [{ label: 'View evidence', to: `/cases/${caseId}/evidence` }];
    case 'entity':
    case 'relationship':
      return [{ label: 'Show in graph', to: `/cases/${caseId}/graph` }];
    case 'event':
      return [{ label: 'Show timeline', to: `/cases/${caseId}/timeline` }];
    case 'location':
      return [{ label: 'Show on map', to: `/cases/${caseId}/map` }];
    case 'finding':
      return [{
        label: 'View finding',
        to: r.finding_type === 'CONTRADICTION'
          ? `/cases/${caseId}/contradictions`
          : `/cases/${caseId}/investigation`,
      }];
    case 'hypothesis':
      return [{ label: 'View hypothesis', to: `/cases/${caseId}/hypotheses` }];
    default:
      return [];
  }
}

const STATUS_PRESENTATION = {
  answered: { variant: 'success', label: 'answered' },
  not_enough_data: { variant: 'warning', label: 'not enough confirmed data' },
  unsupported: { variant: 'warning', label: 'outside the case record' },
  error: { variant: 'danger', label: 'error' },
};

function recordBits(r) {
  if (!r) return null;
  const bits = [];
  if (r.entity_type) bits.push(r.entity_type);
  if (r.relationship_type) bits.push(`${r.source || '?'} → ${r.target || '?'}`);
  if (r.evidence_type) bits.push(r.evidence_type);
  if (r.source_reference) bits.push(r.source_reference);
  if (r.timestamp) bits.push(r.timestamp);
  if (r.object_value) bits.push(r.object_value);
  if (r.confidence_band) bits.push(r.confidence_band);
  return bits.length ? bits.join(' · ') : null;
}

/** Compact, intent-aware rendering of the structured facts (no JSON dump). */
function StructuredFacts({ data }) {
  const rows = [];
  if (data?.counts) {
    rows.push(['confirmed records',
      `${data.counts.entities || 0} entities · ${data.counts.relationships || 0} relationships · ` +
      `${data.counts.evidence || 0} evidence · ${data.counts.timeline_events || 0} events`]);
  }
  if (Array.isArray(data?.events)) {
    rows.push(['timeline', data.events.length
      ? data.events.slice(0, 6).map((e) =>
        `${e.timestamp || 'undated'} — ${e.type} ${e.entity ? `(${e.entity})` : ''}`)
        .join(' · ')
      : 'no dated events on record']);
  }
  if (Array.isArray(data?.contradictions)) {
    rows.push(['potential contradictions', data.contradictions.length
      ? data.contradictions.slice(0, 5).map((c) => `${c.title || `#${c.id}`}`).join(' · ')
      : 'none detected in the confirmed records']);
  }
  if (Array.isArray(data?.gaps)) {
    rows.push(['evidence gaps', data.gaps.length
      ? data.gaps.slice(0, 5).map((g) => g.title || `#${g.id}`).join(' · ')
      : 'none flagged']);
  }
  if (Array.isArray(data?.hypotheses)) {
    rows.push(['hypotheses', data.hypotheses.length
      ? data.hypotheses.slice(0, 5).map((h) =>
        `${h.title || `#${h.id}`} (${h.confidence_band || h.band || 'unbanded'})`).join(' · ')
      : 'none generated']);
  }
  if (Array.isArray(data?.locations)) {
    rows.push(['locations', data.locations.length
      ? data.locations.map((l) =>
        `${l.name || `#${l.id}`}${l.claims?.length ? ` (${l.claims.length} claim${l.claims.length > 1 ? 's' : ''})` : ''}`)
        .join(' · ')
      : '—']);
  }
  if (data?.edges_removed != null) {
    rows.push(['simulation',
      `${data.edges_removed} edge(s) would be removed — simulation only, nothing changed`]);
  }
  if (data?.hits?.length) {
    rows.push(['search hits', data.hits.slice(0, 6).map((h) => h.label).join(' · ')]);
  }
  if (!rows.length) return null;
  return (
    <dl className="grid gap-1.5">
      {rows.map(([k, v]) => (
        <div key={k} className="flex flex-wrap gap-x-2">
          <dt className="label-micro min-w-[150px]">{k}</dt>
          <dd className="text-[12px] text-navy-600">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function CaseCopilotPage() {
  const { caseFile: c } = useCaseFile();
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState(null);
  const [history, setHistory] = useState([]);

  const { data: status, error: statusError, loading: statusLoading, reload } =
    useCnaResource(() => copilotService.caseStatus(c.id), [c.id]);
  const { data: sug } = useCnaResource(
    () => copilotService.suggestions(c.id), [c.id]);

  const suggested = useMemo(() => sug?.suggestions || [], [sug]);
  const activeProvider = useMemo(
    () => status?.providers?.find((p) => p.id === status?.active),
    [status]);

  const submit = async (text) => {
    const q = (text ?? question).trim();
    if (!q || asking) return;
    setAsking(true);
    setAskError(null);
    try {
      const b = await copilotService.ask(c.id, q);
      setAnswer(b);
      setQuestion('');
      setHistory((h) => [{ question: q, at: new Date().toISOString() }, ...h].slice(0, 8));
    } catch (e) {
      setAskError(e);
    } finally {
      setAsking(false);
    }
  };

  if (statusLoading && !status) return <PageLoader label="Checking the case copilot…" />;
  if (statusError && !status) {
    const offline = statusError instanceof V1Error && statusError.offline;
    return (
      <div>
        <PageHeader title="Copilot" description="Grounded, cited Q&A for this case file." />
        <ErrorState
          title={offline ? 'Copilot backend unreachable' : 'Could not load copilot status'}
          description={statusError.message}
          onRetry={reload}
        />
      </div>
    );
  }

  const forbidden = askError instanceof V1Error && askError.status === 403;
  const st = STATUS_PRESENTATION[answer?.status] || STATUS_PRESENTATION.error;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Copilot"
        description="Ask about the confirmed records of this case — people, links, timeline, locations, contradictions, gaps and what-if simulation. Every answer cites the records behind it; the engine is deterministic and uses neutral, reviewable language."
        actions={
          <Badge variant={activeProvider?.active ? 'success' : 'warning'} dot>
            engine: {activeProvider?.name || status?.active || '—'}
          </Badge>
        }
      />

      <Card>
        <CardHeader
          title="Ask"
          subtitle="English, हिन्दी, मराठी or اردو — the answer comes back in the language you ask"
          actions={activeProvider?.model
            ? <Badge variant="neutral">{activeProvider.model}</Badge>
            : <Badge variant="neutral">no LLM key configured</Badge>}
        />
        <div className="space-y-3 p-4 pt-1">
          <div className="flex items-end gap-2">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit();
              }}
              rows={2}
              maxLength={500}
              placeholder="e.g. How are Rajesh Kumar and Vikram Rao connected?  ·  राजेश कुमार कोणाशी जोडलेला आहे?"
              className="w-full resize-y rounded-md border border-line bg-white px-3 py-2 text-[13px] leading-relaxed text-navy-800 placeholder:text-navy-300 focus:border-accent focus:outline-none"
            />
            <Button icon={ArrowUp} loading={asking} disabled={!question.trim() || forbidden}
              onClick={() => submit()}>
              Ask
            </Button>
          </div>
          <p className="figure text-[10.5px] text-navy-300">
            {question.length}/500 · Ctrl/⌘+Enter to ask · read-only — asking never writes to the case
          </p>

          {suggested.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="label-micro">Suggested</span>
              {suggested.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={asking}
                  onClick={() => submit(s)}
                  className="rounded-full border border-line bg-slate-50/60 px-2.5 py-1 text-[11.5px] text-navy-600 transition-colors hover:border-line-strong hover:bg-white hover:text-navy-800"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {forbidden && (
            <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              Your role can read this case but cannot ask the copilot (INVESTIGATOR or above is
              required). Read-only case tools remain available.
            </p>
          )}
          {!forbidden && askError && (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700">
              {askError.message}
            </p>
          )}
        </div>
      </Card>

      {answer ? (
        <Card>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line px-5 py-3">
            <Badge variant={st.variant} dot>{st.label}</Badge>
            <Badge variant="neutral">{answer.intent}</Badge>
            {answer.data?.question_language && answer.data.question_language !== 'en' && (
              <Badge variant="info">
                asked in {LANGUAGE_NAMES[answer.data.question_language] || answer.data.question_language}
              </Badge>
            )}
            {answer.data?.answer_language && answer.data.answer_language !== 'en' && (
              <Badge variant="teal">
                answered in {LANGUAGE_NAMES[answer.data.answer_language] || answer.data.answer_language}
              </Badge>
            )}
            <span className="figure ml-auto text-[10.5px] text-navy-300">
              {answer.interpretation}
            </span>
          </div>

          <div className="space-y-4 px-5 py-4">
            {answer.answer_text ? (
              <p className="whitespace-pre-line text-[13.5px] leading-relaxed text-navy-800">
                {answer.answer_text}
              </p>
            ) : (
              <p className="text-[13px] text-navy-400">
                No prose answer — the structured result below is the full answer.
              </p>
            )}

            <StructuredFacts data={answer.data} />

            {answer.data?.localization_note && (
              <p className="flex items-start gap-2 rounded-md border border-line bg-slate-50/60 px-3 py-2 text-[11.5px] text-navy-400">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                {answer.data.localization_note}
              </p>
            )}

            <div className="grid gap-x-8 gap-y-2 rounded-md border border-line-soft bg-slate-50/40 px-4 py-3 sm:grid-cols-2">
              <div>
                <p className="label-micro">Confidence</p>
                <div className="mt-1 flex items-center gap-2">
                  <div className="h-1.5 w-28 overflow-hidden rounded-full bg-line-soft">
                    <div
                      className="h-full rounded-full bg-accent"
                      style={{ width: `${Math.round((answer.confidence || 0) * 100)}%` }}
                    />
                  </div>
                  <span className="figure text-[11.5px] text-navy-600">
                    {Math.round((answer.confidence || 0) * 100)}%
                  </span>
                </div>
                {answer.confidence_basis && (
                  <p className="mt-1 text-[11.5px] leading-relaxed text-navy-400">
                    {answer.confidence_basis}
                  </p>
                )}
              </div>
              <div>
                <p className="label-micro">Provider</p>
                <p className="mt-0.5 text-[12px] text-navy-600">{answer.provider}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-navy-400">
                  Deterministic engine over confirmed records — no language model was used to
                  generate the facts above.
                </p>
              </div>
            </div>

            {answer.citations?.length > 0 && (
              <div>
                <p className="label-micro">Cited records ({answer.citations.length})</p>
                <ul className="mt-1.5 divide-y divide-line-soft">
                  {answer.citations.map((cit) => {
                    const Icon = KIND_ICON[cit.kind] || FileText;
                    return (
                      <li key={`${cit.kind}-${cit.id}`}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                        <span className="flex items-center gap-1.5 text-[12.5px] text-navy-700">
                          <Icon className="h-3.5 w-3.5 text-navy-300" aria-hidden />
                          <Badge variant="neutral">{cit.kind}</Badge>
                          <span className="font-medium">{cit.label}</span>
                        </span>
                        {recordBits(cit.record) && (
                          <span className="figure text-[10.5px] text-navy-400">
                            {recordBits(cit.record)}
                          </span>
                        )}
                        <span className="ml-auto flex items-center gap-2">
                          {citationLinks(c.id, cit).map((l) => (
                            <Link
                              key={l.to + l.label}
                              to={l.to}
                              className="inline-flex items-center gap-1 text-[11.5px] font-medium text-accent hover:underline"
                            >
                              <ExternalLink className="h-3 w-3" aria-hidden />
                              {l.label}
                            </Link>
                          ))}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {answer.suggestions?.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 border-t border-line-soft pt-3">
                <Sparkles className="h-3.5 w-3.5 text-navy-300" aria-hidden />
                {answer.suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    disabled={asking}
                    onClick={() => submit(s)}
                    className="rounded-full border border-line bg-white px-2.5 py-1 text-[11.5px] text-navy-600 transition-colors hover:border-line-strong hover:text-navy-800"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        </Card>
      ) : (
        !asking && (
          <Card>
            <div className="flex flex-col items-center px-6 py-10 text-center">
              <Bot className="h-6 w-6 text-navy-200" aria-hidden />
              <h3 className="mt-3 text-sm font-semibold text-navy-800">
                Ask about the confirmed records
              </h3>
              <p className="mt-1 max-w-md text-[12.5px] leading-relaxed text-navy-400">
                Answers are generated only from what is confirmed in this case — people, links,
                events, locations, claims and findings. If the case does not hold the evidence,
                the copilot says so instead of guessing.
              </p>
            </div>
          </Card>
        )
      )}

      {history.length > 1 && (
        <Card>
          <CardHeader
            title="Earlier questions"
            actions={<button type="button" className="inline-flex items-center gap-1 text-[11px] text-navy-300 hover:text-navy-500"
              onClick={() => { setHistory([]); setAnswer(null); }}><X className="h-3 w-3" aria-hidden />clear</button>}
          />
          <ul className="divide-y divide-line-soft">
            {history.slice(1).map((h, i) => (
              <li key={h.at + i}>
                <button
                  type="button"
                  onClick={() => submit(h.question)}
                  className="block w-full px-5 py-2.5 text-left text-[12.5px] text-navy-600 transition-colors hover:bg-slate-50/60 hover:text-navy-800"
                >
                  {h.question}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="flex items-center gap-2 text-[11.5px] text-navy-300">
        <Network className="h-3.5 w-3.5 shrink-0" aria-hidden />
        Answers reference confirmed case data only. Neutral terminology is used throughout
        (potential connection, potential contradiction, requires review) — the copilot never
        states conclusions of guilt.
      </p>
    </div>
  );
}
