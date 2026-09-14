import { createContext, useContext } from 'react';
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom';
import { ServerOff } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { StatusBadge, PriorityBadge } from '@/components/cases/StatusBadge';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService, V1Error } from '@/services/v1';
import { v1CaseTabs } from '@/lib/navigation';
import { formatDateTime, cn } from '@/lib/utils';

export const CaseFileContext = createContext(null);

/** The loaded case file for the route tree under /cases/:caseId. */
export function useCaseFile() {
  return useContext(CaseFileContext);
}

/**
 * Case file shell: loads the case once and hands it to every tab through
 * context. Sub-resources (entities, evidence, …) are fetched by the tabs
 * themselves, so switching tabs never re-fetches the case header.
 */
export function CaseLayout() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { data: caseFile, error, loading, reload } = useCnaResource(
    () => caseService.getCase(caseId),
    [caseId]
  );

  if (loading && !caseFile) return <PageLoader label={`Loading case ${caseId}…`} />;

  if (error && !caseFile) {
    const offline = error instanceof V1Error && error.offline;
    return (
      <div className="py-10">
        <ErrorState
          title={offline ? 'Case backend unreachable' : 'Case not available'}
          description={
            offline
              ? 'The case area is live-backed and has no offline fallback. Start the backend (python3 backend/run.py) and retry.'
              : error.message
          }
          onRetry={reload}
          action={<Button variant="outline" icon={ServerOff} onClick={() => navigate('/cases')}>All cases</Button>}
        />
      </div>
    );
  }

  const c = caseFile;
  return (
    <CaseFileContext.Provider value={{ caseFile: c, caseId, reload }}>
      <div className="space-y-5">
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="figure text-[12px] text-navy-400">{c.case_number}</span>
            <StatusBadge status={c.status} />
            <PriorityBadge priority={c.priority} />
            {c.is_synthetic && (
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-navy-300">
                synthetic demonstration data
              </span>
            )}
          </div>
          <h1 className="font-display text-[26px] leading-[1.15] text-navy-900">{c.title}</h1>
          {c.description && (
            <p className="max-w-3xl text-[13px] leading-relaxed text-navy-400">{c.description}</p>
          )}
          <p className="text-[11.5px] text-navy-300">
            Opened {formatDateTime(c.created_at)} by {c.created_by_name || 'unknown'}
          </p>
        </header>

        <nav
          className="flex flex-wrap items-center gap-1 border-b border-line pb-px"
          aria-label="Case tools"
        >
          {v1CaseTabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={`/cases/${c.id}${tab.to ? `/${tab.to}` : ''}`}
              end={tab.end}
              className={({ isActive }) =>
                cn(
                  'border-b-2 px-3 py-2 text-[12.5px] font-medium transition-colors',
                  isActive
                    ? 'border-accent text-navy-900'
                    : 'border-transparent text-navy-400 hover:border-line-strong hover:text-navy-700'
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>

        <Outlet />
      </div>
    </CaseFileContext.Provider>
  );
}
