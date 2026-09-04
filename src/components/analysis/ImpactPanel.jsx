import { useState } from 'react';
import { FlaskConical, ShieldCheck, ArrowRight, Unlink, UserMinus, Split, TrendingUp } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { cnaService } from '@/services';
import { cnaContradictionType, cnaFindingType } from '@/lib/cna';
import { cn } from '@/lib/utils';

/**
 * Evidence impact — "what would this case look like without this record?"
 *
 * The backend re-runs the entire pipeline with the record withheld and diffs
 * the result against the case as recorded. Nothing is modified, and the panel
 * says so: this is a thought experiment about how much of the current picture
 * rests on one record, not a claim that the record is wrong.
 */
export function ImpactPanel({ sources = [], records = [], label }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await cnaService.getImpact({ sources, records }));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  };

  if (error) return <AnalysisError error={error} onRetry={run} compact />;

  if (!result) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 p-3.5">
        <p className="text-[12.5px] leading-relaxed text-navy-500">
          Withhold {label} and re-run the case to see how much of the current picture depends on it.
          Nothing is modified.
        </p>
        <Button
          className="mt-2.5"
          variant="outline"
          size="sm"
          icon={FlaskConical}
          onClick={run}
          loading={running}
          disabled={running}
        >
          Simulate withholding this evidence
        </Button>
      </div>
    );
  }

  const s = result.summary;

  return (
    <div className="animate-fade-in space-y-3 rounded-xl border-2 border-dashed border-amber-300 bg-amber-50/40 p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.12em] text-amber-800">
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
          Simulation — the case was not changed
        </p>
        <Badge variant="warning" dot>
          Counterfactual
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Delta label="Links" before={s.links_before} after={s.links_after} />
        <Delta label="Subjects" before={s.subjects_before} after={s.subjects_after} />
        <Delta label="Contradictions" before={s.contradictions_before} after={s.contradictions_after} />
        <Delta label="Patterns" before={s.findings_before} after={s.findings_after} />
      </div>

      {result.contradictions_resolved?.length > 0 && (
        <Section icon={ShieldCheck} title={`Contradictions that disappear (${result.contradictions_resolved.length})`}>
          {result.contradictions_resolved.map((c, i) => (
            <li key={i} className="text-[12.5px] leading-relaxed text-navy-600">
              <span className="font-medium">{cnaContradictionType(c.type).label}</span> — {c.title}
            </li>
          ))}
        </Section>
      )}

      {result.contradictions_introduced?.length > 0 && (
        <Section icon={FlaskConical} title={`Contradictions that appear instead (${result.contradictions_introduced.length})`}>
          {result.contradictions_introduced.map((c, i) => (
            <li key={i} className="text-[12.5px] leading-relaxed text-navy-600">
              <span className="font-medium">{cnaContradictionType(c.type).label}</span> — {c.title}
            </li>
          ))}
        </Section>
      )}

      {result.identity_splits?.length > 0 && (
        <Section icon={Split} title={`Identities that come apart (${result.identity_splits.length})`}>
          {result.identity_splits.map((x, i) => (
            <li key={i} className="text-[12.5px] leading-relaxed text-navy-600">
              {x.detail}
            </li>
          ))}
        </Section>
      )}

      {result.removed_links?.length > 0 && (
        <Section icon={Unlink} title={`Links that disappear (${result.removed_links.length})`}>
          {result.removed_links.slice(0, 8).map((l, i) => (
            <li key={i} className="text-[12.5px] text-navy-600">
              {l.a_label} <span className="text-navy-300">↔</span> {l.b_label}
              <span className="ml-1.5 text-[11px] text-navy-400">
                {l.types.join(', ').toLowerCase().replace(/_/g, ' ')}
              </span>
            </li>
          ))}
          {result.removed_links.length > 8 && (
            <li className="text-[11.5px] text-navy-400">+{result.removed_links.length - 8} more</li>
          )}
        </Section>
      )}

      {result.isolated_subjects?.length > 0 && (
        <Section icon={UserMinus} title={`Subjects left unconnected (${result.isolated_subjects.length})`}>
          {result.isolated_subjects.map((x, i) => (
            <li key={i} className="text-[12.5px] text-navy-600">
              <span className="font-medium">{x.subject}</span> — {x.detail}
            </li>
          ))}
        </Section>
      )}

      {result.findings_resolved?.length > 0 && (
        <Section icon={ShieldCheck} title={`Patterns that no longer fire (${result.findings_resolved.length})`}>
          {result.findings_resolved.slice(0, 6).map((f, i) => (
            <li key={i} className="text-[12.5px] text-navy-600">
              <span className="font-medium">{cnaFindingType(f.type).label}</span> — {f.title}
            </li>
          ))}
        </Section>
      )}

      {result.influence_changes?.length > 0 && (
        <Section icon={TrendingUp} title={`Ranking changes (${result.influence_changes.length})`}>
          {result.influence_changes.slice(0, 6).map((x, i) => (
            <li key={i} className="font-mono text-[12px] text-navy-600">
              {x.subject}: #{x.rank_before} <ArrowRight className="inline h-3 w-3" aria-hidden />{' '}
              {x.rank_after ? `#${x.rank_after}` : 'unranked'}
            </li>
          ))}
        </Section>
      )}

      {s.links_removed === 0 &&
        !result.contradictions_resolved?.length &&
        !result.findings_resolved?.length &&
        !result.influence_changes?.length && (
          <p className="text-[12.5px] leading-relaxed text-navy-500">
            Nothing in the current picture depends on this record alone — every link it supports is
            attested elsewhere.
          </p>
        )}

      <p className="border-t border-amber-200/70 pt-2.5 text-[11px] leading-relaxed text-navy-400">
        {result.method} {result.disclaimer}
      </p>
    </div>
  );
}

function Delta({ label, before, after }) {
  const changed = before !== after;
  return (
    <div className="rounded-lg border border-slate-200 bg-white/60 p-2 dark:bg-transparent">
      <p className="text-[9.5px] font-semibold uppercase tracking-[0.1em] text-navy-300">{label}</p>
      <p className="mt-0.5 font-mono text-[13px] font-semibold text-navy-700">
        {before}
        <ArrowRight className="mx-1 inline h-3 w-3 text-navy-300" aria-hidden />
        <span className={cn(changed ? 'text-amber-700' : 'text-navy-400')}>{after}</span>
      </p>
    </div>
  );
}

function Section({ icon: Icon, title, children }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-400">
        <Icon className="h-3 w-3" aria-hidden />
        {title}
      </p>
      <ul className="mt-1.5 space-y-1">{children}</ul>
    </div>
  );
}
