import { useState } from 'react';
import { MessagesSquare, Send, Lightbulb, AlertTriangle } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { EmptyState } from '@/components/ui/EmptyState';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { EvidenceTrail } from '@/components/analysis/EvidenceTrail';
import { SubjectDrawer } from '@/components/analysis/SubjectDrawer';
import { MarkdownReport } from '@/components/analysis/MarkdownReport';
import { cnaService } from '@/services';
import { cnaEdgeLabel, cnaNodeType, cnaSeverity, cnaSourceType, formatINR, formatScore } from '@/lib/cna';
import { inputBase } from '@/components/ui/Input';
import { cn, formatDate } from '@/lib/utils';

const SUGGESTIONS = [
  'How is Rajesh Kumar Singh connected to Vikram Sethi?',
  'Who are the top 5 key people?',
  'Show suspicious patterns',
  'Everyone connected to Fareed Shaikh within 2 hops',
  'Transactions over 10 lakh',
  'What groups exist in this network?',
];

/**
 * Renders whichever result shape the parsed intent produced.
 *
 * The backend answers different questions with different structures, so this
 * switches on the intent it reported rather than guessing from the payload.
 */
function Answer({ parsed, result, onSubject, onTrail }) {
  if (result === null || result === undefined) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="No result for that interpretation"
        description="The parser understood the question but the graph had nothing to answer it with."
        compact
      />
    );
  }

  const intent = parsed?.intent;

  if (intent === 'influencers') {
    return (
      <Table>
        <THead>
          <Tr>
            <Th className="w-14">Rank</Th>
            <Th>Subject</Th>
            <Th className="w-24">Score</Th>
            <Th>Why</Th>
          </Tr>
        </THead>
        <TBody>
          {result.map((r) => (
            <Tr key={r.id} onClick={() => onSubject(r.id)}>
              <Td className="font-mono text-[12px] text-navy-400">#{r.rank}</Td>
              <Td className="font-medium text-navy-800">{r.label}</Td>
              <Td className="font-mono text-[12px] font-semibold">{formatScore(r.score)}</Td>
              <Td className="text-[12px] leading-relaxed text-navy-500">{r.why}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    );
  }

  if (intent === 'anomalies') {
    return (
      <div className="space-y-2.5">
        {result.map((f) => {
          const sev = cnaSeverity(f.severity);
          return (
            <div key={f.id} className="rounded-lg border border-slate-200 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[13px] font-medium text-navy-800">{f.title}</p>
                <Badge variant={sev.variant}>{sev.label}</Badge>
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-navy-500">{f.description}</p>
              {f.basis?.rule && <p className="mt-1.5 font-mono text-[11px] text-navy-400">Rule: {f.basis.rule}</p>}
            </div>
          );
        })}
      </div>
    );
  }

  if (intent === 'communities') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        {result.map((group, i) => (
          <div key={i} className="rounded-lg border border-slate-200 p-3">
            <p className="text-[13px] font-semibold text-navy-800">
              Group {i} <span className="font-normal text-navy-400">· {group.length} members</span>
            </p>
            <ul className="mt-1.5 space-y-0.5">
              {group.map((m) => {
                // Groups arrive either as ids or as {id,label} objects.
                const id = typeof m === 'string' ? m : m.id;
                const label = typeof m === 'string' ? m : m.label;
                return (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => onSubject(id)}
                      className="text-left text-[12px] text-navy-500 hover:text-teal-700"
                    >
                      {label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    );
  }

  if (intent === 'transactions') {
    return (
      <Table>
        <THead>
          <Tr>
            <Th>From</Th>
            <Th>To</Th>
            <Th className="w-32 text-right">Amount</Th>
            <Th className="w-32">Date</Th>
            <Th className="w-28">Channel</Th>
          </Tr>
        </THead>
        <TBody>
          {result.map((t, i) => (
            <Tr key={t.txn_id || i}>
              <Td>
                <span className="font-medium text-navy-800">{t.from_name}</span>
                <span className="mt-0.5 block font-mono text-[11px] text-navy-300">{t.from_account}</span>
              </Td>
              <Td>
                <span className="font-medium text-navy-800">{t.to_name}</span>
                <span className="mt-0.5 block font-mono text-[11px] text-navy-300">{t.to_account}</span>
              </Td>
              <Td className="text-right font-mono text-[12px] font-semibold">{formatINR(t.amount_inr)}</Td>
              <Td className="text-[12px] text-navy-500">{formatDate(t.timestamp || t.date)}</Td>
              <Td className="text-[12px] text-navy-500">{t.channel || t.mode || '—'}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    );
  }

  if (intent === 'calls') {
    return (
      <Table>
        <THead>
          <Tr>
            <Th>Link</Th>
            <Th className="w-48">Sources</Th>
            <Th className="w-24 text-right">Confidence</Th>
            <Th className="w-24" />
          </Tr>
        </THead>
        <TBody>
          {result.map((c) => (
            <Tr key={`${c.a}|${c.b}`}>
              <Td>
                <span className="font-medium text-navy-800">{c.a_label}</span>
                <span className="mx-1.5 text-navy-300">↔</span>
                <span className="font-medium text-navy-800">{c.b_label}</span>
              </Td>
              <Td>
                <span className="flex flex-wrap gap-1">
                  {(c.independent_sources || []).map((s) => (
                    <Badge key={s} variant="teal">
                      {cnaSourceType(s).label}
                    </Badge>
                  ))}
                </span>
              </Td>
              <Td className="text-right font-mono text-[12px]">{formatScore(c.confidence, 2)}</Td>
              <Td>
                <button
                  type="button"
                  onClick={() => onTrail({ a: c.a, b: c.b })}
                  className="text-[12px] font-medium text-teal-700 hover:text-teal-800"
                >
                  Evidence
                </button>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    );
  }

  if (intent === 'neighbourhood') {
    return (
      <div>
        <p className="mb-2.5 text-[13px] text-navy-500">
          {result.nodes?.length || 0} entities and {result.edges?.length || 0} relationships around{' '}
          <span className="font-medium text-navy-800">
            {result.nodes?.find((n) => n.id === result.center)?.label || result.center}
          </span>
          .
        </p>
        <div className="flex flex-wrap gap-1.5">
          {(result.nodes || []).map((n) => {
            const meta = cnaNodeType(n.type);
            return (
              <button
                key={n.id}
                type="button"
                onClick={() => onSubject(n.id)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                  n.id === result.center
                    ? 'bg-teal-600 text-white'
                    : 'bg-slate-100 text-navy-600 hover:bg-slate-200'
                )}
              >
                <meta.icon className="h-3 w-3" aria-hidden />
                {n.label}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  if (intent === 'path') {
    if (!result.paths?.length) {
      return (
        <EmptyState
          title="No connection within the hop limit"
          description="Absence of a path is not evidence that no relationship exists — only that no record the pipeline read connects them."
          compact
        />
      );
    }
    return (
      <div className="space-y-3">
        {result.narrative?.text && (
          <p className="rounded-lg border border-slate-200 bg-slate-50/70 px-3.5 py-3 text-[13px] leading-relaxed text-navy-600">
            {result.narrative.text}
          </p>
        )}
        {result.paths.map((p, pi) => (
          <div key={pi} className="rounded-lg border border-slate-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[13px] font-semibold text-navy-800">
                Route {pi + 1} · {p.hops} hop{p.hops === 1 ? '' : 's'}
              </p>
              <Badge variant="neutral">confidence {formatScore(p.path_confidence, 2)}</Badge>
            </div>
            <p className="mt-1.5 text-[13px] text-navy-600">{(p.labels || []).join('  →  ')}</p>
            <div className="mt-2 space-y-1">
              {(p.legs || []).map((leg, li) => (
                <div key={li} className="flex items-start justify-between gap-2 text-[12px] text-navy-500">
                  <span>
                    {leg.from_label} → {leg.to_label} ·{' '}
                    {(leg.types || []).map(cnaEdgeLabel).join(', ')}
                  </span>
                  <button
                    type="button"
                    onClick={() => onTrail({ a: leg.from, b: leg.to })}
                    className="shrink-0 font-medium text-teal-700 hover:text-teal-800"
                  >
                    Evidence
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (intent === 'entity') {
    return (
      <div className="space-y-3">
        <p className="text-[13px] leading-relaxed text-navy-600">{result.narrative?.text}</p>
        <MarkdownReport markdown={result.markdown} />
        <Button variant="outline" size="sm" onClick={() => onSubject(result.node)}>
          Full profile
        </Button>
      </div>
    );
  }

  // Unknown intent — show the payload rather than pretend to render it.
  return (
    <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 font-mono text-[11px] leading-relaxed text-navy-600">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

export function AskPage() {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [subjectId, setSubjectId] = useState(null);
  const [trail, setTrail] = useState(null);

  async function submit(q) {
    const text = (q ?? question).trim();
    if (!text || pending) return;
    setPending(true);
    setError(null);
    try {
      const answer = await cnaService.ask(text);
      setHistory((h) => [{ id: Date.now(), question: text, ...answer }, ...h]);
      setQuestion('');
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Ask a question"
          subtitle="The parser is intent-based, not a general text-to-query engine — so it always restates its own interpretation, and a misread question is visible immediately."
        />
        <CardBody className="space-y-3">
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="min-w-[260px] flex-1">
              <label htmlFor="q" className="mb-1.5 block text-[13px] font-medium text-navy-700">
                Question
              </label>
              <input
                id="q"
                className={inputBase}
                placeholder="How is Rajesh Kumar Singh connected to Vikram Sethi?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
            </div>
            <Button type="submit" icon={Send} loading={pending} disabled={!question.trim()}>
              Ask
            </Button>
          </form>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="flex items-center gap-1.5 text-[12px] font-medium text-navy-500">
              <Lightbulb className="h-3.5 w-3.5" aria-hidden />
              Try
            </span>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                disabled={pending}
                onClick={() => submit(s)}
                className="rounded-lg bg-slate-100 px-2.5 py-1 text-[12px] font-medium text-navy-500 transition-colors hover:bg-slate-200 disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>

          {error && <AnalysisError error={error} onRetry={() => setError(null)} compact />}
        </CardBody>
      </Card>

      {pending && (
        <Card>
          <CardBody>
            <AnalysisSkeleton rows={4} />
          </CardBody>
        </Card>
      )}

      {history.length === 0 && !pending ? (
        <Card>
          <EmptyState
            icon={MessagesSquare}
            title="No questions asked yet"
            description="Ask in plain English, or pick one of the suggestions above."
          />
        </Card>
      ) : (
        history.map((entry) => (
          <Card key={entry.id}>
            <CardHeader
              title={entry.question}
              subtitle="What the system understood, and what it answered."
            />
            <CardBody className="space-y-3.5">
              {/* The interpretation is stated before the answer, deliberately. */}
              <div className="rounded-lg border border-teal-200 bg-teal-50/50 px-3.5 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-teal-700">Interpreted as</p>
                <p className="mt-1 text-[13px] leading-relaxed text-navy-700">{entry.parsed?.interpretation}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <Badge variant="teal">intent: {entry.parsed?.intent || 'unknown'}</Badge>
                  <Badge variant="neutral">parser confidence {formatScore(entry.parsed?.confidence, 2)}</Badge>
                  {(entry.parsed?.unresolved || []).map((u) => (
                    <Badge key={u} variant="warning">
                      unresolved: {u}
                    </Badge>
                  ))}
                </div>
                {(entry.parsed?.unresolved || []).length > 0 && (
                  <p className="mt-2 text-[12px] leading-relaxed text-amber-700">
                    Part of the question could not be resolved to anything in the graph. Treat the answer as partial.
                  </p>
                )}
              </div>

              <Answer
                parsed={entry.parsed}
                result={entry.result}
                onSubject={setSubjectId}
                onTrail={setTrail}
              />
            </CardBody>
          </Card>
        ))
      )}

      <AnalysisDisclosure />

      <SubjectDrawer nodeId={subjectId} open={Boolean(subjectId)} onClose={() => setSubjectId(null)} />
      <EvidenceTrail pair={trail} open={Boolean(trail)} onClose={() => setTrail(null)} />
    </div>
  );
}
