import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Crown, FileDown, Search, ArrowRight } from 'lucide-react';
import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { SubjectDrawer } from '@/components/analysis/SubjectDrawer';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { cnaService } from '@/services';
import { CNA_INFLUENCE_COMPONENTS, cnaNodeType, formatScore } from '@/lib/cna';
import { cn } from '@/lib/utils';

const COMPONENT_LABEL = Object.fromEntries(CNA_INFLUENCE_COMPONENTS.map((c) => [c.key, c.label]));
const COMPONENT_HINT = Object.fromEntries(CNA_INFLUENCE_COMPONENTS.map((c) => [c.key, c.hint]));

/**
 * The influence model is a weighted sum, so each component's Shapley value has
 * a closed form and is computed exactly rather than sampled. The six
 * attributions therefore sum precisely to the gap between this subject's score
 * and the network average — which this panel shows rather than asserts.
 */
function AttributionChart({ subject }) {
  const data = useMemo(() => {
    if (!subject?.attribution) return [];
    return CNA_INFLUENCE_COMPONENTS.map((c) => ({
      key: c.key,
      label: c.label,
      value: Number(subject.attribution[c.key] ?? 0),
    })).sort((a, b) => b.value - a.value);
  }, [subject]);

  if (!data.length) return null;

  const sum = data.reduce((acc, d) => acc + d.value, 0);
  const gap = Number(subject.score) - Number(subject.baseline);
  // Both numbers come from the backend; showing them together is the check.
  const reconciles = Math.abs(sum - gap) < 0.005;

  return (
    <div>
      <div className="h-[210px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
            <XAxis type="number" tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} />
            <YAxis
              type="category"
              dataKey="label"
              width={92}
              tick={{ fontSize: 11, fill: '#334155' }}
              tickLine={false}
              axisLine={false}
            />
            <RTooltip
              cursor={{ fill: '#f1f5f9' }}
              contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12 }}
              formatter={(v, _n, item) => [formatScore(v, 4), COMPONENT_HINT[item.payload.key] || 'Contribution']}
            />
            <ReferenceLine x={0} stroke="#94a3b8" />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
              {data.map((d) => (
                <Cell key={d.key} fill={d.value >= 0 ? '#0d9488' : '#e11d48'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2.5 text-[12px] leading-relaxed text-navy-500">
        Network average <span className="font-mono font-semibold text-navy-800">{formatScore(subject.baseline)}</span>
        {' + '}attributions <span className="font-mono font-semibold text-navy-800">{formatScore(sum, 4)}</span>
        {' = '}score <span className="font-mono font-semibold text-navy-800">{formatScore(subject.score)}</span>.{' '}
        {reconciles ? (
          <span className="text-emerald-700">The six attributions reconcile exactly to the gap from the average.</span>
        ) : (
          <span className="text-amber-700">Attributions do not reconcile — treat this ranking as unverified.</span>
        )}
      </div>

      {/* The chart's values, reachable without hovering. */}
      <Table className="mt-3 min-w-0">
        <THead>
          <Tr>
            <Th>Component</Th>
            <Th className="w-24 text-right">Normalised</Th>
            <Th className="w-28 text-right">Attribution</Th>
          </Tr>
        </THead>
        <TBody>
          {data.map((d) => (
            <Tr key={d.key}>
              <Td>
                <span className="font-medium text-navy-800">{d.label}</span>
                <span className="mt-0.5 block text-[11px] text-navy-400">{COMPONENT_HINT[d.key]}</span>
              </Td>
              <Td className="text-right font-mono text-[12px]">{formatScore(subject.components?.[d.key])}</Td>
              <Td
                className={cn(
                  'text-right font-mono text-[12px] font-semibold',
                  d.value >= 0 ? 'text-teal-700' : 'text-rose-600'
                )}
              >
                {d.value >= 0 ? '+' : ''}
                {formatScore(d.value, 4)}
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

export function KeyPeoplePage() {
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(searchParams.get('subject') || null);
  const [drawerId, setDrawerId] = useState(null);
  const [exportingId, setExportingId] = useState(null);

  const { data, error, loading, reload } = useCnaResource(() => cnaService.getInfluencers(50), []);

  // A deep link (?subject=) selects that subject once the ranking arrives.
  useEffect(() => {
    const param = searchParams.get('subject');
    if (param) setSelectedId(param);
  }, [searchParams]);

  const ranked = data || [];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ranked;
    return ranked.filter((r) => String(r.label || '').toLowerCase().includes(q));
  }, [ranked, query]);

  const selected = useMemo(
    () => ranked.find((r) => r.id === selectedId) || filtered[0] || ranked[0] || null,
    [ranked, filtered, selectedId]
  );

  function select(id) {
    setSelectedId(id);
    setSearchParams(id ? { subject: id } : {}, { replace: true });
  }

  async function exportSubjectPdf(subject) {
    setExportingId(subject.id);
    try {
      const { bytes } = await cnaService.downloadEntityPdf(subject.id, subject.label);
      toast.success(
        `Subject profile exported (${(bytes / 1024).toFixed(0)} KB)`,
        'The SHA-256 digest printed on the document matches the audit entry recorded when it was made.'
      );
    } catch (e) {
      toast.error('Export failed', e.message);
    } finally {
      setExportingId(null);
    }
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
          title="Key individuals"
          subtitle="Ranked by a weighted sum of betweenness, PageRank, degree, eigenvector centrality, prior record and cross-group bridging. The model is additive, so each component's contribution is attributed exactly."
        />
      </Card>

      <div className="grid gap-5 lg:grid-cols-5">
        {/* Ranking */}
        <Card className="lg:col-span-3">
          <CardHeader
            title={`Ranking${ranked.length ? ` · ${filtered.length} of ${ranked.length}` : ''}`}
            actions={
              <div className="w-56">
                <Input
                  icon={Search}
                  placeholder="Search subjects…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search subjects"
                />
              </div>
            }
          />
          <CardBody className="p-0">
            {loading && !data ? (
              <div className="p-5">
                <AnalysisSkeleton rows={8} />
              </div>
            ) : filtered.length === 0 ? (
              <p className="px-5 py-10 text-center text-[13px] text-navy-400">
                No subject matches “{query}”.
              </p>
            ) : (
              <Table>
                <THead>
                  <Tr>
                    <Th className="w-14">Rank</Th>
                    <Th>Subject</Th>
                    <Th className="w-24">Score</Th>
                    <Th className="w-36">Top driver</Th>
                    <Th className="w-20">Group</Th>
                  </Tr>
                </THead>
                <TBody>
                  {filtered.map((r) => {
                    const meta = cnaNodeType(r.type);
                    const active = selected?.id === r.id;
                    return (
                      <Tr key={r.id} onClick={() => select(r.id)} selected={active}>
                        <Td className="font-mono text-[12px] text-navy-400">#{r.rank}</Td>
                        <Td>
                          <span className="flex items-center gap-2">
                            <meta.icon className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                            <span className={cn('font-medium', active ? 'text-teal-700' : 'text-navy-800')}>
                              {r.label}
                            </span>
                          </span>
                        </Td>
                        <Td>
                          <span className="flex items-center gap-2">
                            <span className="font-mono text-[12px] font-semibold text-navy-800">
                              {formatScore(r.score)}
                            </span>
                            <span className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-100">
                              <span
                                className="block h-full rounded-full bg-teal-500"
                                style={{ width: `${Math.min(100, Number(r.score) * 100)}%` }}
                              />
                            </span>
                          </span>
                        </Td>
                        <Td>
                          <Badge variant="teal">{COMPONENT_LABEL[r.top_driver] || r.top_driver}</Badge>
                        </Td>
                        <Td className="text-navy-500">{r.community}</Td>
                      </Tr>
                    );
                  })}
                </TBody>
              </Table>
            )}
          </CardBody>
        </Card>

        {/* Attribution for the selected subject */}
        <Card className="lg:col-span-2">
          {loading && !data ? (
            <CardBody>
              <AnalysisSkeleton rows={6} />
            </CardBody>
          ) : !selected ? (
            <CardBody>
              <p className="py-10 text-center text-[13px] text-navy-400">Select a subject to see its attribution.</p>
            </CardBody>
          ) : (
            <>
              <CardHeader
                title={selected.label}
                subtitle={`Rank ${selected.rank} · group ${selected.community} · why this score is above or below the network average`}
                actions={<Crown className="h-4 w-4 text-amber-500" aria-hidden />}
              />
              <CardBody className="space-y-4">
                <p className="rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5 text-[13px] leading-relaxed text-navy-600">
                  {selected.why}
                </p>

                <AttributionChart subject={selected} />

                <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                  <Button variant="outline" size="sm" icon={ArrowRight} onClick={() => setDrawerId(selected.id)}>
                    Full profile
                  </Button>
                  <Button
                    variant="subtle"
                    size="sm"
                    icon={FileDown}
                    loading={exportingId === selected.id}
                    onClick={() => exportSubjectPdf(selected)}
                  >
                    Export PDF
                  </Button>
                </div>
              </CardBody>
            </>
          )}
        </Card>
      </div>

      <AnalysisDisclosure />

      <SubjectDrawer nodeId={drawerId} open={Boolean(drawerId)} onClose={() => setDrawerId(null)} />
    </div>
  );
}
