import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, Filter, HelpCircle } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/EmptyState';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { SubjectDrawer } from '@/components/analysis/SubjectDrawer';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { CNA_FINDING_TYPES, cnaFindingType, cnaSeverity, cnaSourceType, formatINR } from '@/lib/cna';
import { cn } from '@/lib/utils';

const SEVERITIES = [
  { id: 'all', label: 'All' },
  { id: 'high', label: 'High' },
  { id: 'medium', label: 'Medium' },
  { id: 'low', label: 'Low' },
];

/** Keys whose values read better as currency. */
const MONEY_KEYS = new Set(['amount', 'total', 'threshold', 'amount_inr', 'total_inr', 'median_amount']);

/**
 * The numbers the rule actually used. A detector that shows its working can be
 * argued with; one that shows only a verdict cannot.
 */
function BasisTable({ basis }) {
  const entries = Object.entries(basis || {}).filter(([k]) => k !== 'rule');
  if (!entries.length) return null;

  return (
    <dl className="mt-2.5 grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-3 border-b border-slate-100 pb-1">
          <dt className="text-[11px] uppercase tracking-wide text-navy-400">{key.replace(/_/g, ' ')}</dt>
          <dd className="font-mono text-[12px] font-medium text-navy-800">
            {Array.isArray(value)
              ? value.join(', ')
              : MONEY_KEYS.has(key) && typeof value === 'number'
                ? formatINR(value)
                : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function PatternsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [severity, setSeverity] = useState(searchParams.get('severity') || 'all');
  const [type, setType] = useState(searchParams.get('type') || 'all');
  const [query, setQuery] = useState('');
  const [subjectId, setSubjectId] = useState(null);

  const { data, error, loading, reload } = useCnaResource(() => cnaService.getFindings(), []);
  const findings = data || [];

  const typeCounts = useMemo(() => {
    const counts = new Map();
    findings.forEach((f) => counts.set(f.type, (counts.get(f.type) || 0) + 1));
    return counts;
  }, [findings]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return findings.filter((f) => {
      if (severity !== 'all' && f.severity !== severity) return false;
      if (type !== 'all' && f.type !== type) return false;
      if (!q) return true;
      return (
        String(f.title).toLowerCase().includes(q) ||
        String(f.description).toLowerCase().includes(q) ||
        (f.entity_labels || []).some((l) => String(l).toLowerCase().includes(q))
      );
    });
  }, [findings, severity, type, query]);

  function updateFilter(next) {
    const params = {};
    const sev = next.severity ?? severity;
    const ty = next.type ?? type;
    if (sev !== 'all') params.severity = sev;
    if (ty !== 'all') params.type = ty;
    setSearchParams(params, { replace: true });
    if (next.severity !== undefined) setSeverity(next.severity);
    if (next.type !== undefined) setType(next.type);
  }

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
          title="Suspicious patterns"
          subtitle="Nine detectors, each stating the rule that fired and the numbers behind it. These are leads to check, not conclusions."
        />
        <CardBody className="space-y-3">
          {/* Severity */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 text-[12px] font-medium text-navy-500">
              <Filter className="h-3.5 w-3.5" aria-hidden />
              Severity
            </span>
            {SEVERITIES.map((s) => {
              const count =
                s.id === 'all' ? findings.length : findings.filter((f) => f.severity === s.id).length;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => updateFilter({ severity: s.id })}
                  className={cn(
                    'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                    severity === s.id
                      ? 'bg-teal-600 text-white'
                      : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
                  )}
                >
                  {s.label} <span className="opacity-70">{count}</span>
                </button>
              );
            })}
          </div>

          {/* Detector */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-medium text-navy-500">Detector</span>
            <button
              type="button"
              onClick={() => updateFilter({ type: 'all' })}
              className={cn(
                'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                type === 'all' ? 'bg-navy-800 text-white' : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
              )}
            >
              All
            </button>
            {Object.entries(CNA_FINDING_TYPES).map(([key, meta]) => {
              const count = typeCounts.get(key) || 0;
              return (
                <button
                  key={key}
                  type="button"
                  disabled={count === 0}
                  onClick={() => updateFilter({ type: key })}
                  title={meta.question}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                    type === key
                      ? 'bg-navy-800 text-white'
                      : count === 0
                        ? 'cursor-not-allowed bg-slate-50 text-navy-200'
                        : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
                  )}
                >
                  <meta.icon className="h-3 w-3" aria-hidden />
                  {meta.label}
                  <span className="opacity-70">{count}</span>
                </button>
              );
            })}
          </div>

          <div className="max-w-sm">
            <Input
              icon={Search}
              placeholder="Search findings and subjects…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search findings"
            />
          </div>
        </CardBody>
      </Card>

      {loading && !data ? (
        <Card>
          <CardBody>
            <AnalysisSkeleton rows={6} />
          </CardBody>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            title="No findings match these filters"
            description="Clear a filter, or widen the search. An absent finding means the rule did not fire — never that something was cleared."
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((f) => {
            const meta = cnaFindingType(f.type);
            const sev = cnaSeverity(f.severity);
            return (
              <Card key={f.id}>
                <CardBody className="space-y-2.5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-2.5">
                      <span
                        className={cn(
                          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                          f.severity === 'high' ? 'bg-rose-50 text-rose-600' : 'bg-amber-50 text-amber-600'
                        )}
                      >
                        <meta.icon className="h-4 w-4" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="text-[14px] font-semibold text-navy-900">{f.title}</p>
                        <p className="mt-0.5 text-[12px] text-navy-400">
                          {meta.label}
                          <span className="mx-1.5 text-navy-200" aria-hidden>
                            •
                          </span>
                          <span className="font-mono">{f.id}</span>
                        </p>
                      </div>
                    </div>
                    <Badge variant={sev.variant} dot>
                      {sev.label}
                    </Badge>
                  </div>

                  <p className="text-[13px] leading-relaxed text-navy-600">{f.description}</p>

                  {meta.question && (
                    <p className="flex items-start gap-1.5 text-[12px] italic leading-relaxed text-navy-400">
                      <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                      {meta.question}
                    </p>
                  )}

                  {/* Subjects named */}
                  {(f.entity_labels || []).length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] uppercase tracking-wide text-navy-400">Subjects</span>
                      {f.entity_labels.map((label, i) => (
                        <button
                          key={`${label}-${i}`}
                          type="button"
                          onClick={() => f.entities?.[i] && setSubjectId(f.entities[i])}
                          className="rounded-md bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-700 ring-1 ring-inset ring-teal-600/20 transition-colors hover:bg-teal-100"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* The rule and its numbers */}
                  <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">Rule that fired</p>
                    <p className="mt-1 font-mono text-[12px] text-navy-700">{f.basis?.rule || '—'}</p>
                    <BasisTable basis={f.basis} />
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] uppercase tracking-wide text-navy-400">Sources</span>
                    {(f.sources || []).map((s) => (
                      <Badge key={s} variant="neutral">
                        {cnaSourceType(String(s).toLowerCase()).label}
                      </Badge>
                    ))}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}

      <AnalysisDisclosure />

      <SubjectDrawer nodeId={subjectId} open={Boolean(subjectId)} onClose={() => setSubjectId(null)} />
    </div>
  );
}
