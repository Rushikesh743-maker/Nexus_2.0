import { useCallback, useEffect, useState } from 'react';
import { NavLink, Navigate, Outlet, useLocation, useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  CalendarDays,
  FolderOpen,
  Network,
  Map as MapIcon,
  History,
  Lightbulb,
  FileText,
  AlertTriangle,
  Upload,
  ClipboardList,
  Layers,
  Bot,
  Radar
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { Breadcrumb } from '@/components/ui/Breadcrumb';
import { PageLoader } from '@/components/ui/LoadingState';
import { CopilotDrawer } from '@/components/intelligence/CopilotDrawer';
import { ErrorState } from '@/components/ui/ErrorState';
import { Button, buttonClasses } from '@/components/ui/Button';
import { investigationService } from '@/services';
import { INVESTIGATION_STATUS, PRIORITY, caseTypeLabel } from '@/lib/constants';
import { Link } from 'react-router-dom';
import { formatDate, timeAgo, cn } from '@/lib/utils';

const TABS = [
  { to: '', label: 'Overview', icon: FileText, end: true, stat: null },
  { to: 'workspace', label: 'Workspace', icon: Layers, stat: null },
  { to: 'evidence', label: 'Evidence', icon: FolderOpen, stat: 'evidence' },
  { to: 'network', label: 'Network', icon: Network, stat: 'relationships' },
  { to: 'map', label: 'Map', icon: MapIcon, stat: 'locations' },
  { to: 'timeline', label: 'Timeline', icon: History, stat: 'events' },
  { to: 'intelligence', label: 'Intelligence', icon: Lightbulb, stat: 'insights' },
  { to: 'reports', label: 'Reports', icon: ClipboardList, stat: null },
];

const ANALYSIS_TAB = { to: 'analysis', label: 'Network Analysis', icon: Radar, stat: null };

/** True for a case whose data lives in the analysis backend, not the mock store. */
export function isAnalysisCase(investigation) {
  return investigation?.analysisBackend === 'cna';
}

/**
 * Tab set for a case.
 *
 * A criminal-network-analysis case has no rows in the mock evidence, entity or
 * event stores — its records are held by the FastAPI pipeline. Showing the
 * standard tabs for it would render empty states over a case that actually has
 * dozens of entities, so it gets the analysis surfaces instead. Every other
 * case keeps exactly the tabs it had.
 */
function tabsFor(investigation) {
  return isAnalysisCase(investigation) ? [ANALYSIS_TAB] : TABS;
}

export function InvestigationLayout() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [investigation, setInvestigation] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  // Deep link: ?copilot=1 opens the assistant (used by Demo Mode).
  useEffect(() => {
    if (searchParams.get('copilot') === '1') {
      setCopilotOpen(true);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    investigationService
      .getById(id)
      .then((inv) => {
        setInvestigation(inv);
        setLoading(false);
      })
      .catch((e) => {
        setError(e);
        setLoading(false);
      });
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Scroll to top between case sub-pages.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  if (loading) return <PageLoader label="Opening case file…" />;

  if (error || !investigation) {
    return (
      <ErrorState
        title="Case file not found"
        description={error?.message || 'The investigation you requested does not exist or was archived.'}
        action={
          <Link to="/investigations" className={buttonClasses('primary', 'sm')}>
            Back to investigations
          </Link>
        }
      />
    );
  }

  // An analysis-backed case has no mock overview to show; its landing screen is
  // the analysis dashboard.
  if (isAnalysisCase(investigation) && location.pathname.replace(/\/$/, '') === `/investigations/${investigation.id}`) {
    return <Navigate to={`/investigations/${investigation.id}/analysis`} replace />;
  }

  const status = INVESTIGATION_STATUS[investigation.status] || INVESTIGATION_STATUS.closed;
  const priority = PRIORITY[investigation.priority] || PRIORITY.low;

  return (
    <div className="space-y-5">
      {/* Case header */}
      <Card>
        <div className="px-5 pb-0 pt-4">
          <div className="flex items-center justify-between gap-3">
            <Breadcrumb
              items={[{ label: 'Investigations', to: '/investigations' }, { label: investigation.code }]}
            />
            <Link to="/investigations" className="flex items-center gap-1 text-[12px] font-medium text-navy-400 transition-colors hover:text-teal-700">
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
              All cases
            </Link>
          </div>
        </div>

        <div className="px-5 pb-4 pt-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="figure rounded bg-slate-50 px-1.5 py-0.5 text-[11px] font-medium text-navy-500">{investigation.code}</span>
                <Badge variant={priority.variant}>{priority.label} priority</Badge>
              </div>
              <h1 className="mt-2.5 font-display text-[24px] leading-tight text-navy-900">{investigation.title}</h1>
              <p className="mt-1 text-[13px] font-medium text-navy-500">
                {caseTypeLabel(investigation.caseType)}
                <span className="mx-1.5 text-navy-200" aria-hidden>•</span>
                <Badge variant={status.variant} dot className="align-middle">
                  {status.label}
                </Badge>
              </p>
            </div>

            {/* Header actions */}
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {!isAnalysisCase(investigation) && (
                <>
                  <Button
                    variant="primary"
                    icon={Upload}
                    onClick={() => navigate(`/investigations/${investigation.id}/evidence?log=1`)}
                  >
                    Upload Evidence
                  </Button>
                  <Button
                    variant="outline"
                    icon={ClipboardList}
                    onClick={() => navigate(`/investigations/${investigation.id}/reports?request=1`)}
                  >
                    Generate Report
                  </Button>
                </>
              )}
              <Button variant="subtle" icon={Bot} onClick={() => setCopilotOpen(true)}>
                Copilot
              </Button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-navy-400">
            <span className="flex items-center gap-1.5">
              <CalendarDays className="h-3.5 w-3.5" aria-hidden />
              Created: <span className="font-medium text-navy-600">{formatDate(investigation.openedAt)}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <Avatar name={investigation.lead?.name || '?'} size="xs" />
              Lead: <span className="font-medium text-navy-600">{investigation.lead?.name || 'Unassigned'}</span>
            </span>
            {investigation.team.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="flex -space-x-1.5">
                  {investigation.team.map((m) => (
                    <Avatar key={m.id} name={m.name} size="xs" ring />
                  ))}
                </span>
                Team of {investigation.team.length + 1}
              </span>
            )}
            {investigation.jurisdiction && (
              <span className="flex items-center gap-1.5">
                <MapPin className="h-3.5 w-3.5" aria-hidden />
                {investigation.jurisdiction}
              </span>
            )}
            <span>Updated {timeAgo(investigation.updatedAt)}</span>
          </div>

          {(investigation.tags || []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {investigation.tags.map((tag) => (
                <Badge key={tag} variant="teal">
                  {tag}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/*
          Sub navigation. An analysis-backed case has exactly one tab, and a
          tab bar holding a single tab is chrome that carries no choice — so it
          is omitted and the analysis sub-nav becomes the only row.
        */}
        {tabsFor(investigation).length > 1 && (
        <nav className="flex gap-0.5 overflow-x-auto border-t border-line-soft px-3 scrollbar-thin" aria-label="Case sections">
          {tabsFor(investigation).map((tab) => {
            const count = tab.stat ? investigation.stats[tab.stat] : null;
            return (
              <NavLink
                key={tab.to}
                to={tab.to ? `/investigations/${investigation.id}/${tab.to}` : `/investigations/${investigation.id}`}
                end={tab.end}
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-[12.5px] font-medium transition-colors duration-150',
                    isActive
                      ? 'border-navy-900 text-navy-900'
                      : 'border-transparent text-navy-400 hover:text-navy-800'
                  )
                }
              >
                <tab.icon className="h-3.5 w-3.5" aria-hidden />
                {tab.label}
                {count !== null && count !== undefined && (
                  <span className="figure rounded bg-slate-50 px-1.5 py-px text-[10px] font-semibold text-navy-500">
                    {count}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
        )}
      </Card>

      <Outlet context={{ investigation, refresh: load }} />

      <CopilotDrawer
        open={copilotOpen}
        onClose={() => setCopilotOpen(false)}
        investigationId={investigation.id}
      />
    </div>
  );
}

export function useInvestigation() {
  return useOutletContext();
}
