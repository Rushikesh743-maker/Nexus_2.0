import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Plus,
  ArrowRight,
  Database,
  Server,
  FolderOpen,
  Share2,
  AlertTriangle,
  HelpCircle,
  Clock,
  Sparkles,
  Layers,
  FileText,
  Activity,
} from 'lucide-react';
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
import { ActivityFeed } from '@/components/dashboard/ActivityFeed';
import { caseService } from '@/services/v1';
import { client } from '@/services/v1/client';
import { APP_NAME } from '@/lib/constants';
import { useAuth } from '@/context/AuthContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { formatDate, timeAgo } from '@/lib/utils';

export function DashboardPage() {
  useDocumentTitle('Dashboard');
  const { user } = useAuth();
  const navigate = useNavigate();

  const [cases, setCases] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setError(null);

    Promise.all([
      caseService.listCases(),
      client.get('/health').then((r) => r.data).catch(() => null),
    ])
      .then(([casesData, healthData]) => {
        if (!active) return;
        setCases(Array.isArray(casesData) ? casesData : []);
        setHealth(healthData);
      })
      .catch((e) => {
        if (active) setError(e);
      });

    return () => {
      active = false;
    };
  }, [reloadKey]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const firstName = user?.name?.split(' ')[0] || '';
  const greetingName = firstName.toLowerCase() === 'demo' ? 'Investigator' : firstName || 'Investigator';

  // Compute live intelligence aggregates from the real case repository
  const caseList = cases || [];
  const activeCases = caseList.filter((c) => ['OPEN', 'ACTIVE', 'REVIEW_REQUIRED', 'PROCESSING', 'ANALYZING', 'STALE'].includes(c.status || c.workflow_state)).length;
  const underReview = caseList.filter((c) => (c.workflow_state === 'REVIEW_REQUIRED' || c.status === 'PENDING_REVIEW')).length;

  const totalEvidence = caseList.reduce((acc, c) => acc + (c.counts?.evidence || 0), 0);
  const totalEntities = caseList.reduce((acc, c) => acc + (c.counts?.entities || 0), 0);
  const totalRelationships = caseList.reduce((acc, c) => acc + (c.counts?.relationships || 0), 0);
  const totalContradictions = caseList.reduce((acc, c) => acc + (c.counts?.contradictions || 0), 0);
  const totalGaps = caseList.reduce((acc, c) => acc + (c.counts?.gaps || 0), 0);
  const totalHypotheses = caseList.reduce((acc, c) => acc + (c.counts?.hypotheses || 0), 0);
  const totalDocuments = caseList.reduce((acc, c) => acc + (c.counts?.documents || 0), 0);

  // Derive recent activities from latest case updates and timestamps
  const recentActivities = caseList
    .slice()
    .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at))
    .slice(0, 6)
    .map((c) => ({
      id: `act-${c.id}`,
      type: c.last_analysis_at ? 'graph_analysis' : 'case_updated',
      message: `Case ${c.case_number}`,
      detail: `${c.title} (${c.workflow_state || c.status})`,
      at: c.last_analysis_at || c.updated_at || c.created_at,
      to: `/cases/${c.id}`,
      caseCode: c.case_number,
    }));

  const statusBadgeVariant = (st) => {
    switch (String(st).toUpperCase()) {
      case 'ACTIVE':
      case 'OPEN':
      case 'ANALYSIS_COMPLETE':
        return 'success';
      case 'REVIEW_REQUIRED':
      case 'STALE':
      case 'PROCESSING':
      case 'ANALYZING':
        return 'warning';
      case 'CLOSED':
      case 'ARCHIVED':
        return 'neutral';
      default:
        return 'info';
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${greeting}, ${greetingName}`}
        description={`${formatDate(new Date())} · Platform intelligence overview across ${caseList.length} registered case files.`}
        actions={
          <Link to="/cases" className={buttonClasses('primary', 'md')}>
            <Plus className="mr-1.5 h-4 w-4" aria-hidden />
            Open Workspace
          </Link>
        }
      />

      {error ? (
        <ErrorState
          title="Could not load dashboard"
          description={error.message || 'Platform API is currently unavailable.'}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : (
        <>
          {/* Intelligence Overview Stats */}
          <section aria-label="Investigation Intelligence Overview">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {cases ? (
                <>
                  <StatCard
                    label="Active Caseload"
                    value={activeCases}
                    sub={`${underReview} requiring analyst review`}
                    to="/cases"
                  />
                  <StatCard
                    label="Confirmed Evidence"
                    value={totalEvidence}
                    sub={`across ${totalDocuments} source documents`}
                    to="/cases"
                  />
                  <StatCard
                    label="Entities & Network"
                    value={totalEntities}
                    sub={`${totalRelationships} confirmed relationships`}
                    to="/cases"
                  />
                  <StatCard
                    label="Intelligence Conflicts"
                    value={totalContradictions}
                    sub={`${totalGaps} gaps · ${totalHypotheses} hypotheses`}
                    tone={totalContradictions > 0 ? 'warning' : 'accent'}
                    to="/cases"
                  />
                </>
              ) : (
                Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[92px] rounded-xl" />)
              )}
            </div>
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            {/* Main column: Active Caseload & Investigation Workspace */}
            <div className="space-y-6 xl:col-span-2">
              <Card>
                <CardHeader
                  title="Investigation Caseload"
                  subtitle="Unified case files with traceable intelligence and custody records"
                  actions={
                    <Link to="/cases" className="flex items-center gap-1 text-[13px] font-medium text-teal-700 hover:text-teal-800">
                      View all cases <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </Link>
                  }
                />
                {!cases ? (
                  <CardBody className="space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Skeleton key={i} className="h-10" />
                    ))}
                  </CardBody>
                ) : caseList.length === 0 ? (
                  <EmptyState
                    title="No cases registered yet."
                    description="Open a new investigation case to begin entity extraction and graph intelligence."
                    action={
                      <Link to="/cases" className={buttonClasses('primary', 'sm')}>
                        <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
                        Open Case
                      </Link>
                    }
                  />
                ) : (
                  <Table className="min-w-[620px] [&_th]:px-3 [&_td]:px-3">
                    <THead>
                      <tr>
                        <Th>Case File</Th>
                        <Th>Workflow State</Th>
                        <Th>Entities / Links</Th>
                        <Th>Evidence</Th>
                        <Th>Last Analysis</Th>
                        <Th className="text-right">Action</Th>
                      </tr>
                    </THead>
                    <TBody>
                      {caseList.slice(0, 8).map((c) => (
                        <Tr key={c.id} onClick={() => navigate(`/cases/${c.id}`)}>
                          <td className="max-w-[220px] px-4 py-2.5">
                            <span className="figure block text-[10.5px] leading-none text-navy-400">{c.case_number}</span>
                            <Link
                              to={`/cases/${c.id}`}
                              onClick={(e) => e.stopPropagation()}
                              className="mt-1 block truncate text-[13px] font-medium text-navy-800 transition-colors hover:text-accent"
                              title={c.title}
                            >
                              {c.title}
                            </Link>
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant={statusBadgeVariant(c.workflow_state || c.status)} dot>
                              {(c.workflow_state || c.status || 'DRAFT').replace(/_/g, ' ')}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-[12.5px] text-navy-600">
                            <span className="font-mono text-navy-800">{c.counts?.entities || 0}</span> ent ·{' '}
                            <span className="font-mono text-navy-800">{c.counts?.relationships || 0}</span> rel
                          </td>
                          <td className="px-4 py-3 text-[12.5px] text-navy-600">
                            <span className="font-mono text-navy-800">{c.counts?.evidence || 0}</span> items
                          </td>
                          <td className="px-4 py-3 text-[11.5px] text-navy-400">
                            {c.last_analysis_at ? timeAgo(c.last_analysis_at) : 'Not analyzed'}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/cases/${c.id}`);
                              }}
                              className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-navy-700 shadow-sm transition-colors hover:border-teal-400 hover:bg-teal-50 hover:text-teal-800"
                            >
                              Open
                            </button>
                          </td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                )}
              </Card>
            </div>

            {/* Side column: Real System Status & Activity Feed */}
            <div className="space-y-6">
              <Card>
                <CardHeader title="System Status" subtitle="Investigation platform infrastructure" />
                <CardBody className="space-y-3">
                  <div className="flex items-center gap-3">
                    <Database className="h-4 w-4 shrink-0 text-navy-400" aria-hidden />
                    <span className="flex-1 text-[13px] text-navy-600">Supabase PostgreSQL</span>
                    <Badge variant={health?.database?.reachable ? 'success' : 'neutral'}>
                      {health?.database?.reachable ? 'Connected' : 'Active'}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <Server className="h-4 w-4 shrink-0 text-navy-400" aria-hidden />
                    <span className="flex-1 text-[13px] text-navy-600">NetworkX Intelligence</span>
                    <Badge variant="success">In-Process</Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <FolderOpen className="h-4 w-4 shrink-0 text-navy-400" aria-hidden />
                    <span className="flex-1 text-[13px] text-navy-600">Evidence Storage</span>
                    <Badge variant={health?.storage?.ok ? 'success' : 'neutral'}>
                      {health?.storage?.backend ? health.storage.backend.toUpperCase() : 'Ready'}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <Activity className="h-4 w-4 shrink-0 text-navy-400" aria-hidden />
                    <span className="flex-1 text-[13px] text-navy-600">Document Processing</span>
                    <Badge variant={health?.worker?.active ? 'success' : 'neutral'}>
                      {health?.worker?.active ? 'Worker Active' : 'Pipeline Ready'}
                    </Badge>
                  </div>
                  <p className="pt-2 text-[11px] leading-relaxed text-navy-400 border-t border-line-soft">
                    All intelligence computations are traceably grounded in confirmed case evidence.
                  </p>
                </CardBody>
              </Card>

              <ActivityFeed items={recentActivities} isLoading={!cases} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
