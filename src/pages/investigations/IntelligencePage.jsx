import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Lightbulb, Info, Gauge, AlertTriangle, Search, GitBranch, FlaskConical } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Tabs } from '@/components/ui/Tabs';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { InsightCard } from '@/components/intelligence/InsightCard';
import { ReevaluationCard } from '@/components/intelligence/ReevaluationCard';
import { ContradictionPanel } from '@/components/intelligence/ContradictionPanel';
import { HypothesisPanel } from '@/components/intelligence/HypothesisPanel';
import { GapPanel } from '@/components/intelligence/GapPanel';
import { ImpactSimulator } from '@/components/intelligence/ImpactSimulator';
import { useInvestigation } from './InvestigationLayout';
import { analysisService, intelligenceService } from '@/services';
import { INSIGHT_CATEGORIES, INSIGHT_STATUS } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

const TAB_IDS = ['signals', 'contradictions', 'hypotheses', 'gaps', 'simulator'];

/**
 * NEXUS Intelligence Center — the analysis hub for a case.
 * All numbers come from the mock analysis service; no engine runs client-side.
 */
export function IntelligencePage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Intelligence`);
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const tab = TAB_IDS.includes(searchParams.get('tab')) ? searchParams.get('tab') : 'signals';
  const setTab = (id) => {
    const next = new URLSearchParams(searchParams);
    if (id === 'signals') next.delete('tab');
    else next.set('tab', id);
    setSearchParams(next, { replace: true });
  };

  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);

  useEffect(() => {
    let active = true;
    setSummaryError(null);
    analysisService
      .getSummary(investigation.id)
      .then((s) => active && setSummary(s))
      .catch((e) => active && setSummaryError(e));
    return () => {
      active = false;
    };
  }, [investigation.id]);

  /* ---- Signals (insight feed) ---- */
  const [insights, setInsights] = useState(null);
  const [entities, setEntities] = useState([]);
  const [insightError, setInsightError] = useState(null);
  const [filters, setFilters] = useState({ category: 'all', status: 'all' });
  const [busyId, setBusyId] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (tab !== 'signals') return undefined;
    let active = true;
    setInsightError(null);
    Promise.all([
      intelligenceService.getInsights(investigation.id, filters),
      intelligenceService.getEntities(investigation.id),
    ])
      .then(([insightsRes, entitiesRes]) => {
        if (!active) return;
        setInsights(insightsRes);
        setEntities(entitiesRes);
      })
      .catch((e) => active && setInsightError(e));
    return () => {
      active = false;
    };
  }, [investigation.id, filters, reloadKey, tab]);

  const entityById = useMemo(() => Object.fromEntries(entities.map((e) => [e.id, e])), [entities]);

  const markReviewed = async (insight) => {
    setBusyId(insight.id);
    try {
      await intelligenceService.markInsightReviewed(insight.id);
      toast.success('Insight marked as reviewed', insight.title);
      setReloadKey((k) => k + 1);
    } catch (e) {
      toast.error('Could not update insight', e.message);
    } finally {
      setBusyId(null);
    }
  };

  const statCards = summary
    ? [
        { icon: Gauge, label: 'Evidence Confidence', value: `${summary.confidence}%` },
        { icon: AlertTriangle, label: 'Conflicting Evidence', value: summary.conflictingEvidence },
        { icon: Search, label: 'Open Investigation Gaps', value: summary.openGaps },
        { icon: GitBranch, label: 'Active Hypotheses', value: summary.activeHypotheses },
      ]
    : [];

  return (
    <div className="space-y-5">
      {/* Intelligence Center header */}
      <Card>
        <CardBody className="py-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-teal-700">NEXUS Intelligence</p>
          <p className="mt-1 text-[13px] text-navy-500">
            Investigation: <span className="font-semibold text-navy-800">{investigation.title}</span>
            <span className="ml-2 font-mono text-[11px] text-navy-300">{investigation.code}</span>
          </p>
          {summaryError ? (
            <ErrorState compact title="Could not load analysis summary" description={summaryError.message} onRetry={() => setSummaryError(null)} className="mt-3" />
          ) : (
            <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {(statCards.length ? statCards : Array.from({ length: 4 })).map((card, i) =>
                card ? (
                  <div key={card.label} className="rounded-xl border border-slate-200 p-3.5">
                    <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-300">
                      <card.icon className="h-3 w-3" aria-hidden /> {card.label}
                    </p>
                    <p className="mt-1 text-2xl font-semibold leading-none text-navy-900">{card.value}</p>
                  </div>
                ) : (
                  <div key={i} className="h-[74px] animate-pulse rounded-xl bg-slate-100" />
                )
              )}
            </div>
          )}
        </CardBody>
      </Card>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'signals', label: 'Signals', icon: Lightbulb },
          { id: 'contradictions', label: 'Contradictions', icon: AlertTriangle },
          { id: 'hypotheses', label: 'Hypotheses', icon: GitBranch },
          { id: 'gaps', label: 'Gaps', icon: Search },
          { id: 'simulator', label: 'Impact Simulator', icon: FlaskConical },
        ]}
      />

      {tab === 'signals' && (
        <div className="space-y-4">
          <ReevaluationCard investigationId={investigation.id} />

          <Card>
            <CardBody className="flex items-start gap-3 py-3.5">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" aria-hidden />
              <p className="text-[13px] leading-relaxed text-navy-500">
                This feed is served from <strong className="font-semibold text-navy-700">mock data</strong>. In production,
                insight items are produced by backend analysis services and reviewed here before verification.
              </p>
            </CardBody>
          </Card>

          <div className="flex flex-wrap items-center gap-2.5">
            <select
              value={filters.category}
              onChange={(e) => setFilters({ ...filters, category: e.target.value })}
              aria-label="Filter by category"
              className="h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-sm text-navy-700"
            >
              <option value="all">All categories</option>
              {Object.entries(INSIGHT_CATEGORIES).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </select>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              aria-label="Filter by status"
              className="h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-sm text-navy-700"
            >
              <option value="all">All statuses</option>
              {Object.entries(INSIGHT_STATUS).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </select>
            <span className="ml-auto text-[12px] text-navy-300">{insights?.total ?? '…'} insights</span>
          </div>

          {insightError ? (
            <ErrorState title="Could not load insights" description={insightError.message} onRetry={() => setReloadKey((k) => k + 1)} />
          ) : !insights ? (
            <PageLoader label="Loading analysis feed…" />
          ) : insights.items.length === 0 ? (
            <Card>
              <EmptyState icon={Lightbulb} title="No insights for this filter" description="Adjust the filters or wait for the next analysis run." />
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {insights.items.map((insight) => (
                <InsightCard key={insight.id} insight={insight} entityById={entityById} busy={busyId === insight.id} onMarkReviewed={markReviewed} />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'contradictions' && <ContradictionPanel investigationId={investigation.id} />}
      {tab === 'hypotheses' && <HypothesisPanel investigationId={investigation.id} />}
      {tab === 'gaps' && <GapPanel investigationId={investigation.id} />}
      {tab === 'simulator' && <ImpactSimulator investigationId={investigation.id} />}

      <p className="rounded-xl border border-teal-100 bg-teal-50/60 px-4 py-3 text-[12px] leading-relaxed text-teal-900">
        <strong className="font-semibold">Responsible use.</strong> NEXUS provides analytical assistance and investigation
        leads. It does not determine guilt or replace investigator judgment. All analysis on this screen is mock presentation
        data in the frontend-only build.
      </p>
    </div>
  );
}
