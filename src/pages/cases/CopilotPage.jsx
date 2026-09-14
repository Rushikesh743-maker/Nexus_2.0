import { Bot, CheckCircle2, ExternalLink, FileSearch, Languages, Network, ShieldCheck, Sparkles, Timer } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { copilotService, caseService, V1Error } from '@/services/v1';

const CAPABILITIES = [
  { icon: FileSearch, title: 'Grounded Q&A', body: 'Answers only from confirmed case records — people, links, events, locations, claims and findings — each one cited back to the record behind it.' },
  { icon: Network, title: 'Structure + graph + timeline', body: 'Relationship paths, neighbourhoods, the case timeline, contradiction and gap findings, and hypothesis bands.' },
  { icon: ShieldCheck, title: 'What-if simulation', body: 'Simulate removing a single piece of evidence and see what it would isolate — a pure simulation that changes nothing.' },
  { icon: Languages, title: 'Multilingual', body: 'Ask in English, हिन्दी, मराठी or اردو; the answer comes back in the language you asked, over the same confirmed facts.' },
  { icon: Timer, title: 'Honest by design', body: 'No language model is used to generate facts. If the case does not hold the evidence, the copilot says so instead of guessing.' },
];

/**
 * Platform copilot — the capability statement (GET /api/v1/copilot) and a
 * route into the case-level copilot console. The real Q&A runs per case at
 * /cases/:id/copilot, because every answer is scoped to one case file.
 */
export function CopilotPage() {
  const { data, error, loading, reload } = useCnaResource(() => copilotService.status(), []);
  const { data: cases } = useCnaResource(() => caseService.listCases(), []);

  if (loading && !data) return <PageLoader label="Checking copilot status…" />;

  if (error && !data) {
    const offline = error instanceof V1Error && error.offline;
    return (
      <div>
        <PageHeader title="Copilot" description="Conversational assistance for case work." />
        <ErrorState
          title={offline ? 'Copilot backend unreachable' : 'Could not check copilot status'}
          description={error.message}
          onRetry={reload}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Copilot"
        description="Conversational assistance for case work — grounded in the case file, cited to the record, never free-associating about the case."
        actions={<Badge variant="success" dot>{data?.stage || 'stage-5'}</Badge>}
      />

      {data?.message && (
        <p className="max-w-3xl text-[13px] leading-relaxed text-navy-600">{data.message}</p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Live capabilities"
            subtitle="The case copilot answers over confirmed records only"
            actions={<Sparkles className="h-4 w-4 text-navy-300" aria-hidden />}
          />
          <ul className="divide-y divide-line-soft">
            {CAPABILITIES.map((c) => (
              <li key={c.title} className="flex items-start gap-3 px-5 py-3.5">
                <c.icon className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
                <div>
                  <p className="text-[13px] font-medium text-navy-800">{c.title}</p>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-navy-400">{c.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Open the copilot for a case"
            subtitle="Ask from inside a case file — every answer is scoped to that case"
          />
          {(cases?.length ?? 0) === 0 ? (
            <div className="px-5 py-8 text-center">
              <Bot className="mx-auto h-6 w-6 text-navy-200" aria-hidden />
              <p className="mt-3 text-[13px] text-navy-400">
                No cases yet. Open a case file and use its <span className="font-medium text-navy-600">Copilot</span> tab.
              </p>
              <Link to="/cases" className="mt-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-accent hover:underline">
                View cases <ExternalLink className="h-3 w-3" aria-hidden />
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-line-soft">
              {cases.slice(0, 8).map((cse) => (
                <li key={cse.id}>
                  <Link
                    to={`/cases/${cse.id}/copilot`}
                    className="group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-slate-50/70"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-navy-800 group-hover:text-navy-900">{cse.title}</p>
                      <p className="figure text-[10.5px] text-navy-400">
                        {cse.case_number}
                        {cse.counts?.entities != null && <> · {cse.counts.entities} entities</>}
                      </p>
                    </div>
                    <ExternalLink className="h-3.5 w-3.5 text-navy-300 transition-colors group-hover:text-accent" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <p className="flex items-start gap-2 text-[11.5px] leading-relaxed text-navy-300">
        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden />
        Every answer cites the records behind it and uses neutral, reviewable language (potential
        connection, potential contradiction, requires review). The engine is deterministic: no
        language model is used to produce facts, and nothing here states a conclusion of guilt.
      </p>
    </div>
  );
}
