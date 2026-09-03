import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Users,
  Network,
  ShieldAlert,
  Layers,
  FileDown,
  RefreshCw,
  ChevronRight,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { StatCard } from '@/components/cards/StatCard';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton, SyntheticNotice } from '@/components/analysis/AnalysisState';
import { BarRowsPanel } from '@/components/analysis/BarRows';
import { CapabilityStrip } from '@/components/analysis/CapabilityStrip';
import { MarkdownReport } from '@/components/analysis/MarkdownReport';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { cnaService } from '@/services';
import { cnaFindingType, cnaSeverity, cnaSourceType, formatScore } from '@/lib/cna';
import { formatDateTime } from '@/lib/utils';
import { useAnalysisCase } from './AnalysisLayout';

/* Only a status role earns colour on a tile; the rest stay in the accent. */
const TILE_TONES = { subjects: 'accent', links: 'accent', flags: 'critical', groups: 'accent' };

/* The reference console's categorical series, in order. */
const SERIES = [
  'var(--data-sky)',
  'var(--data-violet)',
  'var(--data-emerald)',
  'var(--data-amber)',
  'var(--data-rose)',
  'var(--data-neutral)',
];

export function AnalysisOverviewPage() {
  const { basePath } = useAnalysisCase();
  const navigate = useNavigate();
  const toast = useToast();
  const [exporting, setExporting] = useState(false);

  const dash = useCnaResource(() => cnaService.getDashboard(), []);
  const stats = useCnaResource(() => cnaService.getStats(), []);
  const overview = useCnaResource(() => cnaService.getOverview(), []);

  const activity = useMemo(() => {
    const a = dash.data?.activity;
    if (!a?.weeks?.length) return [];
    return a.weeks.map((week, i) => {
      const row = { week: week.slice(5) };
      a.series.forEach((s) => {
        row[s.label] = s.points[i];
      });
      return row;
    });
  }, [dash.data]);

  async function exportPdf() {
    setExporting(true);
    try {
      const { bytes } = await cnaService.downloadOverviewPdf();
      toast.success(`Case summary exported (${(bytes / 1024).toFixed(0)} KB). A SHA-256 digest is printed on the document.`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setExporting(false);
    }
  }

  function reloadAll() {
    dash.reload();
    stats.reload();
    overview.reload();
  }

  if (dash.error && !dash.data) {
    return (
      <Card>
        <AnalysisError error={dash.error} onRetry={reloadAll} />
      </Card>
    );
  }

  const tiles = dash.data?.tiles || [];
  const severity = dash.data?.severity || [];
  const byType = dash.data?.findings_by_type || [];
  const bySource = dash.data?.by_source || [];
  const corroboration = dash.data?.corroboration || [];
  const topSubjects = dash.data?.top_subjects || [];

  return (
    <div className="space-y-5">
      {/* Headline tiles */}
      {dash.loading && !dash.data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="h-[86px] animate-pulse bg-slate-50" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {tiles.map((t) => (
            <StatCard
              key={t.key}
              tone={TILE_TONES[t.key] || 'accent'}
              label={t.label}
              value={t.value}
              sub={t.hint}
            />
          ))}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Weekly activity */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Network activity by week"
            subtitle="Attributed calls and transactions. Only records the pipeline could attribute to a resolved subject are counted."
          />
          <CardBody>
            {dash.loading && !dash.data ? (
              <AnalysisSkeleton rows={5} />
            ) : activity.length === 0 ? (
              <p className="py-8 text-center text-[13px] text-navy-400">No dated activity in the corpus.</p>
            ) : (
              <>
                <div className="h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={activity} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--viz-grid)" vertical={false} />
                      <XAxis dataKey="week" tick={{ fontSize: 11, fill: 'var(--data-neutral)' }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: 'var(--data-neutral)' }} tickLine={false} axisLine={false} />
                      <RTooltip
                        contentStyle={{
                          borderRadius: 6,
                          border: '1px solid var(--line)',
                          background: 'var(--surface-raised)',
                          color: 'var(--ink-800)',
                          fontSize: 12,
                        }}
                        labelFormatter={(v) => `Week of ${v}`}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      {(dash.data?.activity?.series || []).map((s, i) => (
                        <Line
                          key={s.key}
                          type="monotone"
                          dataKey={s.label}
                          stroke={i === 0 ? 'var(--data-teal)' : 'var(--data-violet)'}
                          strokeWidth={2}
                          dot={{ r: 2.5 }}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Every chart has a table behind it — no value is hover-only. */}
                <details className="mt-3">
                  <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.1em] text-navy-400 transition-colors hover:text-navy-800">
                    Table
                  </summary>
                  <Table className="mt-2 min-w-0">
                    <THead>
                      <Tr>
                        <Th>Week of</Th>
                        {(dash.data?.activity?.series || []).map((s) => (
                          <Th key={s.key}>{s.label}</Th>
                        ))}
                      </Tr>
                    </THead>
                    <TBody>
                      {activity.map((row) => (
                        <Tr key={row.week}>
                          <Td className="font-medium">{row.week}</Td>
                          {(dash.data?.activity?.series || []).map((s) => (
                            <Td key={s.key}>{row[s.label]}</Td>
                          ))}
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                </details>
              </>
            )}
          </CardBody>
        </Card>

        {/* Severity + corroboration */}
        <div className="space-y-5">
          <Card>
            <CardHeader title="Findings by severity" subtitle="Every finding states the rule that fired." />
            <CardBody className="space-y-2.5">
              {dash.loading && !dash.data ? (
                <AnalysisSkeleton rows={2} />
              ) : severity.length === 0 ? (
                <p className="text-[13px] text-navy-400">No findings.</p>
              ) : (
                severity.map((s) => {
                  const meta = cnaSeverity(s.key);
                  return (
                    <Link
                      key={s.key}
                      to={`${basePath}/patterns?severity=${s.key}`}
                      className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2.5 transition-colors hover:bg-slate-50"
                    >
                      <Badge variant={meta.variant} dot>
                        {s.label}
                      </Badge>
                      <span className="flex items-center gap-1 text-sm font-semibold text-navy-900">
                        {s.count}
                        <ChevronRight className="h-3.5 w-3.5 text-navy-200" aria-hidden />
                      </span>
                    </Link>
                  );
                })
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Corroboration"
              subtitle="How many independent source systems support each link."
            />
            <CardBody className="space-y-2">
              {corroboration.map((c) => (
                <div key={c.key} className="flex items-center gap-3">
                  <span className="w-[68px] shrink-0 text-[12px] font-medium text-navy-500">{c.label}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-teal-500"
                      style={{
                        width: `${(c.value / Math.max(...corroboration.map((x) => x.value), 1)) * 100}%`,
                      }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right text-[12px] font-semibold text-navy-800">{c.value}</span>
                </div>
              ))}
              {corroboration.length > 0 && (
                <Link
                  to={`${basePath}/links`}
                  className="mt-1 inline-block text-[12px] font-medium text-teal-700 hover:text-teal-800"
                >
                  Rank links by corroboration →
                </Link>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* What fired — bar rows with a table behind them, as in the console. */}
        <BarRowsPanel
          title="Findings by type"
          caption={`${byType.length} detector${byType.length === 1 ? '' : 's'} fired`}
          valueLabel="Findings"
          rows={byType.map((t) => ({
            key: t.key,
            label: t.label,
            value: t.value,
            /*
             * Uniform accent, as in the reference console. Colouring each bar by
             * whether the detector produced a high-severity finding turned most
             * of the panel red and drowned out the severity split, which has its
             * own panel and is the place that question is actually answered.
             */
            color: 'var(--accent)',
            high: t.high,
          }))}
          onRowClick={(r) => navigate(`${basePath}/patterns?type=${r.key}`)}
        />

        {/* Where the evidence came from */}
        <BarRowsPanel
          title="Where the evidence comes from"
          caption="links attested per source system"
          valueLabel="Relationships"
          rows={bySource.map((sItem, i) => ({
            key: sItem.key,
            label: sItem.label,
            value: sItem.value,
            color: SERIES[i % SERIES.length],
          }))}
        />
      </div>

      {/* Top subjects */}
      <Card>
        <CardHeader
          title="Most influential subjects"
          subtitle="Ranked by an additive model whose components are attributed exactly, not sampled."
          actions={
            <Link to={`${basePath}/people`} className="text-[12px] font-medium text-teal-700 hover:text-teal-800">
              Full ranking with attribution →
            </Link>
          }
        />
        <CardBody className="p-0">
          {dash.loading && !dash.data ? (
            <div className="p-5">
              <AnalysisSkeleton rows={5} />
            </div>
          ) : (
            <Table>
              <THead>
                <Tr>
                  <Th className="w-14">Rank</Th>
                  <Th>Subject</Th>
                  <Th className="w-24">Score</Th>
                  <Th className="w-32">Top driver</Th>
                  <Th className="w-24">Group</Th>
                  <Th className="w-28">Prior cases</Th>
                </Tr>
              </THead>
              <TBody>
                {topSubjects.map((s) => (
                  <Tr key={s.id}>
                    <Td className="font-mono text-[12px] text-navy-400">#{s.rank}</Td>
                    <Td>
                      <Link
                        to={`${basePath}/people?subject=${encodeURIComponent(s.id)}`}
                        className="font-medium text-navy-800 hover:text-teal-700"
                      >
                        {s.label}
                      </Link>
                    </Td>
                    <Td className="font-mono text-[12px] font-semibold text-navy-800">{formatScore(s.value)}</Td>
                    <Td>
                      <Badge variant="teal">{String(s.driver || '').replace(/_/g, ' ')}</Badge>
                    </Td>
                    <Td className="text-navy-500">Group {s.community}</Td>
                    <Td>
                      {s.prior_cases === null || s.prior_cases === undefined ? (
                        <span className="text-[12px] text-navy-300" title="Not present in the criminal-history database">
                          Not found
                        </span>
                      ) : (
                        <span className="font-medium">{s.prior_cases}</span>
                      )}
                    </Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      {/* Case summary */}
      <Card>
        <CardHeader
          title="Case summary"
          subtitle={
            overview.data?.generated_at
              ? `Generated by the report builder from the current graph on ${formatDateTime(overview.data.generated_at)}.`
              : 'Generated by the report builder from the current graph.'
          }
          actions={
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" icon={RefreshCw} onClick={reloadAll}>
                Refresh
              </Button>
              <Button variant="primary" size="sm" icon={FileDown} loading={exporting} onClick={exportPdf}>
                Export PDF
              </Button>
            </div>
          }
        />
        <CardBody>
          {overview.loading && !overview.data ? (
            <AnalysisSkeleton rows={6} />
          ) : overview.error ? (
            <AnalysisError error={overview.error} onRetry={overview.reload} compact />
          ) : (
            <MarkdownReport markdown={overview.data?.markdown} />
          )}
        </CardBody>
      </Card>

      <CapabilityStrip capabilities={stats.data?.capabilities} loading={stats.loading} />

      <SyntheticNotice />
      <AnalysisDisclosure />
    </div>
  );
}
