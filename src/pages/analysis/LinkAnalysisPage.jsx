import { useMemo, useState } from 'react';
import { ArrowRight, FileDown, Route as RouteIcon, Search } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { EmptyState } from '@/components/ui/EmptyState';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { EvidenceTrail } from '@/components/analysis/EvidenceTrail';
import { MarkdownReport } from '@/components/analysis/MarkdownReport';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { cnaService } from '@/services';
import { cnaEdgeLabel, cnaSourceType, formatScore } from '@/lib/cna';
import { cn } from '@/lib/utils';

/** One hop of a connection, with the records that support it. */
function Leg({ leg, index, onTrail }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-[13px] font-medium text-navy-800">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-navy-100 font-mono text-[10px] text-navy-500">
            {index + 1}
          </span>
          {leg.from_label}
          <ArrowRight className="h-3.5 w-3.5 text-navy-300" aria-hidden />
          {leg.to_label}
        </span>
        <span className="flex items-center gap-1.5">
          <Badge variant="neutral">conf {formatScore(leg.confidence, 2)}</Badge>
          <button
            type="button"
            onClick={() => onTrail({ a: leg.from, b: leg.to })}
            className="text-[12px] font-medium text-teal-700 hover:text-teal-800"
          >
            Evidence
          </button>
        </span>
      </div>

      <div className="mt-1.5 flex flex-wrap gap-1">
        {(leg.types || []).map((t) => (
          <Badge key={t} variant="teal">
            {cnaEdgeLabel(t)}
          </Badge>
        ))}
      </div>

      <ul className="mt-2 space-y-1">
        {(leg.sources || []).slice(0, 4).map((s, i) => (
          <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-navy-500">
            <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-navy-200" aria-hidden />
            <span>
              <span className="font-medium text-navy-600">{cnaSourceType(s.source_type).label}</span> — {s.evidence}
            </span>
          </li>
        ))}
        {(leg.sources || []).length > 4 && (
          <li className="pl-3 text-[11px] text-navy-300">
            + {leg.sources.length - 4} more source record{leg.sources.length - 4 === 1 ? '' : 's'}
          </li>
        )}
      </ul>
    </div>
  );
}

export function LinkAnalysisPage() {
  const toast = useToast();
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [cutoff, setCutoff] = useState(5);
  const [submitted, setSubmitted] = useState(null);
  const [trail, setTrail] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [minLevel, setMinLevel] = useState(2);
  const [corroborationQuery, setCorroborationQuery] = useState('');

  const entities = useCnaResource(() => cnaService.getEntities(), []);
  const corroboration = useCnaResource(() => cnaService.getCorroboration(1), []);

  const path = useCnaResource(
    () => cnaService.getPath(submitted.a, submitted.b, submitted.cutoff),
    [submitted?.a, submitted?.b, submitted?.cutoff],
    { enabled: Boolean(submitted) }
  );

  // People are the useful endpoints for a connection analysis.
  const people = useMemo(
    () => (entities.data || []).filter((e) => e.type === 'PERSON').sort((x, y) => x.label.localeCompare(y.label)),
    [entities.data]
  );

  const options = useMemo(
    () => [{ value: '', label: 'Select a subject…' }, ...people.map((p) => ({ value: p.id, label: p.label }))],
    [people]
  );

  const filteredCorroboration = useMemo(() => {
    const q = corroborationQuery.trim().toLowerCase();
    return (corroboration.data || [])
      .filter((c) => c.corroboration_level >= minLevel)
      .filter(
        (c) =>
          !q ||
          String(c.a_label).toLowerCase().includes(q) ||
          String(c.b_label).toLowerCase().includes(q)
      );
  }, [corroboration.data, minLevel, corroborationQuery]);

  async function exportPathPdf() {
    if (!submitted) return;
    setExporting(true);
    try {
      const { bytes } = await cnaService.downloadPathPdf(submitted.a, submitted.b, submitted.cutoff);
      toast.success(`Connection analysis exported (${(bytes / 1024).toFixed(0)} KB)`);
    } catch (e) {
      toast.error('Export failed', e.message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Connection analysis */}
      <Card>
        <CardHeader
          title="Connection analysis"
          subtitle="How two subjects are connected, hop by hop, with the source records behind every leg."
        />
        <CardBody>
          {entities.error ? (
            <AnalysisError error={entities.error} onRetry={entities.reload} compact />
          ) : (
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (a && b && a !== b) setSubmitted({ a, b, cutoff });
              }}
            >
              <div className="w-56">
                <Select label="From" value={a} onChange={(e) => setA(e.target.value)} options={options} />
              </div>
              <div className="w-56">
                <Select label="To" value={b} onChange={(e) => setB(e.target.value)} options={options} />
              </div>
              <div className="w-40">
                <Select
                  label="Max hops"
                  value={String(cutoff)}
                  onChange={(e) => setCutoff(Number(e.target.value))}
                  options={[2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: `${n} hops` }))}
                />
              </div>
              <Button type="submit" icon={RouteIcon} disabled={!a || !b || a === b || entities.loading}>
                Trace connection
              </Button>
              {a && b && a === b && (
                <p className="text-[12px] text-amber-700">Pick two different subjects.</p>
              )}
            </form>
          )}
        </CardBody>
      </Card>

      {/* Result */}
      {submitted && (
        <Card>
          <CardHeader
            title="Result"
            actions={
              path.data && (
                <Button variant="outline" size="sm" icon={FileDown} loading={exporting} onClick={exportPathPdf}>
                  Export PDF
                </Button>
              )
            }
          />
          <CardBody className="space-y-4">
            {path.loading ? (
              <AnalysisSkeleton rows={5} />
            ) : path.error ? (
              <AnalysisError error={path.error} onRetry={path.reload} compact />
            ) : !path.data?.paths?.length ? (
              <EmptyState
                title="No connection found within this many hops"
                description="Widen the hop limit, or accept that these two subjects are not linked by any record the pipeline has read. Absence of a path is not evidence of absence of a relationship."
                compact
              />
            ) : (
              <>
                {path.data.narrative?.text && (
                  <p className="rounded-lg border border-slate-200 bg-slate-50/70 px-3.5 py-3 text-[13px] leading-relaxed text-navy-600">
                    {path.data.narrative.text}
                  </p>
                )}

                {path.data.paths.map((p, pi) => (
                  <div key={pi} className="space-y-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[13px] font-semibold text-navy-800">
                        Route {pi + 1}
                        <span className="ml-2 font-normal text-navy-400">
                          {p.hops} hop{p.hops === 1 ? '' : 's'}
                        </span>
                      </p>
                      <span className="flex items-center gap-1.5">
                        <Badge variant="neutral">path confidence {formatScore(p.path_confidence, 2)}</Badge>
                        {(p.source_types || []).map((s) => (
                          <Badge key={s} variant="teal">
                            {cnaSourceType(s).label}
                          </Badge>
                        ))}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-2">
                      {(p.labels || []).map((label, li) => (
                        <span key={li} className="flex items-center gap-1.5">
                          <span className="text-[12px] font-medium text-navy-700">{label}</span>
                          {li < p.labels.length - 1 && (
                            <ArrowRight className="h-3 w-3 text-navy-300" aria-hidden />
                          )}
                        </span>
                      ))}
                    </div>

                    <div className="space-y-2">
                      {(p.legs || []).map((leg, li) => (
                        <Leg key={li} leg={leg} index={li} onTrail={setTrail} />
                      ))}
                    </div>
                  </div>
                ))}

                {path.data.markdown && (
                  <details className="border-t border-slate-100 pt-3">
                    <summary className="cursor-pointer text-[12px] font-medium text-navy-500 hover:text-teal-700">
                      Full written analysis
                    </summary>
                    <div className="mt-3">
                      <MarkdownReport markdown={path.data.markdown} />
                    </div>
                  </details>
                )}
              </>
            )}
          </CardBody>
        </Card>
      )}

      {/* Corroboration */}
      <Card>
        <CardHeader
          title="Links by corroboration"
          subtitle="How many independent source systems support each link. A link seen by three systems is a very different claim from one seen by a single feed."
          actions={
            <div className="flex items-center gap-2">
              <div className="w-44">
                <Input
                  icon={Search}
                  placeholder="Filter subjects…"
                  value={corroborationQuery}
                  onChange={(e) => setCorroborationQuery(e.target.value)}
                  aria-label="Filter corroborated links"
                />
              </div>
              <div className="w-36">
                <Select
                  value={String(minLevel)}
                  onChange={(e) => setMinLevel(Number(e.target.value))}
                  options={[
                    { value: '1', label: 'All links' },
                    { value: '2', label: '2+ sources' },
                    { value: '3', label: '3+ sources' },
                  ]}
                  aria-label="Minimum corroboration"
                />
              </div>
            </div>
          }
        />
        <CardBody className="p-0">
          {corroboration.loading && !corroboration.data ? (
            <div className="p-5">
              <AnalysisSkeleton rows={6} />
            </div>
          ) : corroboration.error ? (
            <div className="p-5">
              <AnalysisError error={corroboration.error} onRetry={corroboration.reload} compact />
            </div>
          ) : filteredCorroboration.length === 0 ? (
            <EmptyState title="No links at this corroboration level" compact />
          ) : (
            <Table>
              <THead>
                <Tr>
                  <Th>Link</Th>
                  <Th className="w-52">Relationship</Th>
                  <Th className="w-48">Independent sources</Th>
                  <Th className="w-24 text-right">Confidence</Th>
                  <Th className="w-24" />
                </Tr>
              </THead>
              <TBody>
                {filteredCorroboration.map((c) => (
                  <Tr key={`${c.a}|${c.b}`}>
                    <Td>
                      <span className="font-medium text-navy-800">{c.a_label}</span>
                      <span className="mx-1.5 text-navy-300">↔</span>
                      <span className="font-medium text-navy-800">{c.b_label}</span>
                    </Td>
                    <Td>
                      <span className="flex flex-wrap gap-1">
                        {(c.types || []).map((t) => (
                          <Badge key={t} variant="neutral">
                            {cnaEdgeLabel(t)}
                          </Badge>
                        ))}
                      </span>
                    </Td>
                    <Td>
                      <span className="flex flex-wrap items-center gap-1">
                        {(c.independent_sources || []).map((s) => (
                          <Badge key={s} variant="teal">
                            {cnaSourceType(s).label}
                          </Badge>
                        ))}
                        <span
                          className={cn(
                            'ml-1 font-mono text-[11px] font-semibold',
                            c.corroboration_level >= 3 ? 'text-emerald-700' : 'text-navy-400'
                          )}
                        >
                          ×{c.corroboration_level}
                        </span>
                      </span>
                    </Td>
                    <Td className="text-right font-mono text-[12px] font-semibold">
                      {formatScore(c.confidence, 2)}
                    </Td>
                    <Td>
                      <button
                        type="button"
                        onClick={() => setTrail({ a: c.a, b: c.b })}
                        className="text-[12px] font-medium text-teal-700 hover:text-teal-800"
                      >
                        Evidence
                      </button>
                    </Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <AnalysisDisclosure />

      <EvidenceTrail pair={trail} open={Boolean(trail)} onClose={() => setTrail(null)} />
    </div>
  );
}
