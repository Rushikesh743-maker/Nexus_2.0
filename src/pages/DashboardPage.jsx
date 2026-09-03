import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, ArrowRight, Database, Server, KeyRound, ScanLine } from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { buttonClasses } from '@/components/ui/Button';
import { StatCard } from '@/components/cards/StatCard';
import { Table, THead, TBody, Tr, Th } from '@/components/ui/Table';
import { Skeleton } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { QuickActions } from '@/components/dashboard/QuickActions';
import { AnalysisCaseBand } from '@/components/dashboard/AnalysisCaseBand';
import { ActivityFeed } from '@/components/dashboard/ActivityFeed';
import { CasePickerModal } from '@/components/modals/CasePickerModal';
import { investigationService, cnaService } from '@/services';
import { INVESTIGATION_STATUS, APP_NAME } from '@/lib/constants';
import { useAuth } from '@/context/AuthContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { formatDate, timeAgo } from '@/lib/utils';

/*
 * What is actually running. These claims were stale — the analysis pipeline is
 * connected, and the analysis map no longer fetches tiles — and a status panel
 * that misreports the system is worse than no status panel.
 */
const SYSTEM_STATUS = [
  { icon: Database, label: 'Case & evidence data', value: 'Mock dataset', variant: 'warning' },
  { icon: KeyRound, label: 'Identity service', value: 'Demo auth', variant: 'warning' },
  { icon: ScanLine, label: 'Analysis map', value: 'Offline plot, no tiles', variant: 'info' },
];

const PICKER_COPY = {
  upload: {
    title: 'Upload evidence',
    description: 'Choose the investigation this evidence belongs to.',
    ctaLabel: 'Continue',
  },
  network: {
    title: 'View network',
    description: 'Choose the investigation whose link network you want to open.',
    ctaLabel: 'Continue',
  },
  timeline: {
    title: 'View timeline',
    description: 'Choose the investigation whose timeline you want to open.',
    ctaLabel: 'Continue',
  },
};

export function DashboardPage() {
  useDocumentTitle('Dashboard');
  const { user } = useAuth();
  const navigate = useNavigate();

  const [stats, setStats] = useState(null);
  const [list, setList] = useState(null);
  const [activity, setActivity] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [picker, setPicker] = useState(null);
  const [pipelineOnline, setPipelineOnline] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([
      investigationService.getDashboardStats(),
      investigationService.list(),
      investigationService.getRecentActivity(6),
    ])
      .then(([s, l, a]) => {
        if (!active) return;
        setStats(s);
        setList(l);
        setActivity(a);
      })
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [reloadKey]);

  // The status panel reports what it observed, not what it assumes.
  useEffect(() => {
    let active = true;
    cnaService
      .getStats()
      .then(() => active && setPipelineOnline(true))
      .catch(() => active && setPipelineOnline(false));
    return () => {
      active = false;
    };
  }, [reloadKey]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const firstName = user?.name?.split(' ')[0] || '';
  const greetingName = firstName.toLowerCase() === 'demo' ? 'Investigator' : firstName || 'Investigator';

  const allCases = list?.items || [];
  const analysisCase = allCases.find((c) => c.analysisBackend === 'cna') || null;
  // The band already surfaces the analysis case, so the table shows the rest.
  const recent = allCases.filter((c) => c.id !== analysisCase?.id).slice(0, 7);
  const loading = !stats && !error;

  const handlePickerSelect = (inv) => {
    if (!picker) return;
    const targets = {
      upload: `/investigations/${inv.id}/evidence?log=1`,
      network: `/investigations/${inv.id}/network`,
      timeline: `/investigations/${inv.id}/timeline`,
    };
    navigate(targets[picker] || `/investigations/${inv.id}`);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${greeting}, ${greetingName}`}
        description={`${formatDate(new Date())} · Here is the current state of your caseload.`}
        actions={
          <Link to="/investigations/new" className={buttonClasses('primary', 'md')}>
            <Plus className="mr-1.5 h-4 w-4" aria-hidden />
            New Investigation
          </Link>
        }
      />

      {error ? (
        <ErrorState title="Could not load dashboard" description={error.message} onRetry={() => setReloadKey((k) => k + 1)} />
      ) : (
        <>
          {/* Overview stats */}
          <section aria-label="Overview">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {stats ? (
                <>
                  {/*
                    Each tile goes somewhere different. They previously all
                    pointed at /investigations, so four labels offered one
                    destination while looking like four.
                  */}
                  <StatCard
                    label="Active Investigations"
                    value={stats.activeCases}
                    sub={`${stats.underReview} under review`}
                    to="/investigations?status=active"
                  />
                  <StatCard
                    label="Evidence Items"
                    value={stats.evidenceLogged}
                    sub="with chain of custody"
                    onClick={() => setPicker('upload')}
                  />
                  <StatCard
                    label="Entities"
                    value={stats.entitiesTracked}
                    sub={`${stats.relationshipsTracked} relationships mapped`}
                    onClick={() => setPicker('network')}
                  />
                  <StatCard
                    label="Pending Reviews"
                    value={stats.insightsPending}
                    sub="insights awaiting analyst"
                    tone={stats.insightsPending > 0 ? 'warning' : 'accent'}
                    to="/investigations?status=pending_review"
                  />
                </>
              ) : (
                Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[92px] rounded-xl" />)
              )}
            </div>
          </section>

          {/* The one case running on the live pipeline, reachable directly. */}
          {analysisCase && <AnalysisCaseBand investigation={analysisCase} />}

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            {/* Main column */}
            <div className="space-y-6 xl:col-span-2">
              {/* Recent investigations */}
              <Card>
                <CardHeader
                  title="Recent Investigations"
                  subtitle="Latest activity across your case files"
                  actions={
                    <Link to="/investigations" className="flex items-center gap-1 text-[13px] font-medium text-teal-700 hover:text-teal-800">
                      View all <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </Link>
                  }
                />
                {!list ? (
                  <CardBody className="space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Skeleton key={i} className="h-10" />
                    ))}
                  </CardBody>
                ) : recent.length === 0 ? (
                  <EmptyState
                    title="No investigations yet."
                    description="Create an investigation and upload evidence to begin analysis."
                    action={
                      <Link to="/investigations/new" className={buttonClasses('primary', 'sm')}>
                        <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
                        Create Investigation
                      </Link>
                    }
                  />
                ) : (
                  <Table className="min-w-[560px] [&_th]:px-3 [&_td]:px-3">
                    <THead>
                      <tr>
                        <Th>Investigation</Th>
                        <Th>Case Type</Th>
                        <Th>Status</Th>
                        <Th>Last Updated</Th>
                        <Th>Investigator</Th>
                        <Th className="text-right">Action</Th>
                      </tr>
                    </THead>
                    <TBody>
                      {recent.map((inv) => {
                        const status = INVESTIGATION_STATUS[inv.status] || INVESTIGATION_STATUS.closed;
                        return (
                          <Tr key={inv.id} onClick={() => navigate(`/investigations/${inv.id}`)}>
                            <td className="max-w-[220px] px-4 py-2.5">
                              <span className="figure block text-[10.5px] leading-none text-navy-400">{inv.code}</span>
                              <Link
                                to={`/investigations/${inv.id}`}
                                onClick={(e) => e.stopPropagation()}
                                className="mt-1 block truncate text-[13px] font-medium text-navy-800 transition-colors hover:text-accent"
                                title={inv.title}
                              >
                                {inv.title}
                              </Link>
                            </td>
                            <td className="px-4 py-3 text-[13px] text-navy-500">{inv.caseTypeLabel}</td>
                            <td className="px-4 py-3">
                              <Badge variant={status.variant} dot>
                                {status.label}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 text-[12px] text-navy-400">{timeAgo(inv.updatedAt)}</td>
                            <td className="px-4 py-3">
                              <span className="flex items-center gap-2 text-[13px] text-navy-600">
                                <Avatar name={inv.lead?.name || '?'} size="xs" />
                                <span className="truncate">{inv.lead?.name || 'Unassigned'}</span>
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  navigate(`/investigations/${inv.id}`);
                                }}
                                className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-navy-700 shadow-sm transition-colors hover:border-teal-400 hover:bg-teal-50 hover:text-teal-800"
                              >
                                Open
                              </button>
                            </td>
                          </Tr>
                        );
                      })}
                    </TBody>
                  </Table>
                )}
              </Card>

            </div>

            {/* Side column */}
            <div className="space-y-6">
              <QuickActions onPickCase={setPicker} />
              <ActivityFeed items={activity?.items} isLoading={!activity} />

              <Card>
                <CardHeader title="System status" subtitle={`${APP_NAME} frontend preview`} />
                <CardBody className="space-y-3">
                  <div className="flex items-center gap-3">
                    <Server className="h-4 w-4 shrink-0 text-navy-300" aria-hidden />
                    <span className="flex-1 text-[13px] text-navy-600">Analysis pipeline</span>
                    <Badge variant={pipelineOnline === null ? 'neutral' : pipelineOnline ? 'success' : 'warning'}>
                      {pipelineOnline === null ? 'Checking…' : pipelineOnline ? 'Connected' : 'Not running'}
                    </Badge>
                  </div>
                  {SYSTEM_STATUS.map((row) => (
                    <div key={row.label} className="flex items-center gap-3">
                      <row.icon className="h-4 w-4 shrink-0 text-navy-300" aria-hidden />
                      <span className="flex-1 text-[13px] text-navy-600">{row.label}</span>
                      <Badge variant={row.variant}>{row.value}</Badge>
                    </div>
                  ))}
                  <p className="pt-1 text-[11px] leading-relaxed text-navy-300">
                    Case management runs on mock data. The network-analysis case runs on the real pipeline in
                    <span className="figure"> backend/</span>.
                  </p>
                </CardBody>
              </Card>
            </div>
          </div>

          {/* Case picker for case-scoped quick actions */}
          <CasePickerModal
            open={Boolean(picker)}
            onClose={() => setPicker(null)}
            title={picker ? PICKER_COPY[picker].title : ''}
            description={picker ? PICKER_COPY[picker].description : ''}
            ctaLabel={picker ? PICKER_COPY[picker].ctaLabel : 'Continue'}
            onSelect={handlePickerSelect}
          />
        </>
      )}
    </div>
  );
}
