import { createContext, useContext, useMemo } from 'react';
import { NavLink, Outlet, useOutletContext } from 'react-router-dom';
import {
  LayoutDashboard,
  Share2,
  Crown,
  ShieldAlert,
  Route as RouteIcon,
  Workflow,
  MessagesSquare,
  ServerCog,
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import { useInvestigation } from '@/pages/investigations/InvestigationLayout';

const AnalysisCaseContext = createContext(null);

/** Case context plus the base path every analysis link is built from. */
export function useAnalysisCase() {
  const ctx = useContext(AnalysisCaseContext);
  if (!ctx) throw new Error('useAnalysisCase must be used inside AnalysisLayout');
  return ctx;
}

const VIEWS = [
  { to: '', end: true, label: 'Overview', icon: LayoutDashboard },
  { to: 'graph', label: 'Graph', icon: Share2 },
  { to: 'people', label: 'Key People', icon: Crown },
  { to: 'patterns', label: 'Patterns', icon: ShieldAlert },
  { to: 'links', label: 'Link Analysis', icon: RouteIcon },
  { to: 'pipeline', label: 'Pipeline', icon: Workflow },
  { to: 'ask', label: 'Ask', icon: MessagesSquare },
  { to: 'system', label: 'System', icon: ServerCog },
];

/**
 * Shell for the criminal-network-analysis views.
 *
 * Sits inside the case file, so the case header and Copilot stay available,
 * and adds a second row of navigation for the eight analysis surfaces.
 */
export function AnalysisLayout() {
  const { investigation, refresh } = useInvestigation();
  const basePath = `/investigations/${investigation.id}/analysis`;

  const value = useMemo(
    () => ({ investigation, refresh, basePath }),
    [investigation, refresh, basePath]
  );

  return (
    <AnalysisCaseContext.Provider value={value}>
      <div className="space-y-5">
        <Card className="px-2 py-1.5">
          <nav className="flex gap-1 overflow-x-auto scrollbar-thin" aria-label="Analysis views">
            {VIEWS.map((view) => (
              <NavLink
                key={view.to || 'overview'}
                to={view.to ? `${basePath}/${view.to}` : basePath}
                end={view.end}
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors',
                    isActive
                      ? 'bg-teal-50 text-teal-700'
                      : 'text-navy-400 hover:bg-slate-100 hover:text-navy-700'
                  )
                }
              >
                <view.icon className="h-3.5 w-3.5" aria-hidden />
                {view.label}
              </NavLink>
            ))}
          </nav>
        </Card>

        <Outlet context={value} />
      </div>
    </AnalysisCaseContext.Provider>
  );
}

/** Available to analysis pages that prefer the outlet-context convention. */
export function useAnalysisOutlet() {
  return useOutletContext();
}
