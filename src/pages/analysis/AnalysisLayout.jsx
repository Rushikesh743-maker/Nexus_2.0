import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useNavigate, useOutletContext } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { CaseStatusBar } from '@/components/analysis/CaseStatusBar';
import { cn } from '@/lib/utils';
import { useInvestigation } from '@/pages/investigations/InvestigationLayout';

const AnalysisCaseContext = createContext(null);

/** Case context plus the base path every analysis link is built from. */
export function useAnalysisCase() {
  const ctx = useContext(AnalysisCaseContext);
  if (!ctx) throw new Error('useAnalysisCase must be used inside AnalysisLayout');
  return ctx;
}

/**
 * The eight analysis surfaces.
 *
 * Each is bound to a number key, as in the reference console — an analyst
 * presenting a case moves between views constantly, and reaching for a number
 * is faster than aiming at a tab. The number is printed on the tab so the
 * shortcut is discoverable rather than folklore.
 */
const VIEWS = [
  { to: '', end: true, label: 'Overview' },
  { to: 'graph', label: 'Network' },
  { to: 'map', label: 'Map' },
  { to: 'people', label: 'Key People' },
  { to: 'patterns', label: 'Patterns' },
  { to: 'links', label: 'Links' },
  { to: 'pipeline', label: 'Sources' },
  { to: 'ask', label: 'Ask' },
  { to: 'system', label: 'System' },
];

export function AnalysisLayout() {
  const { investigation, refresh } = useInvestigation();
  const navigate = useNavigate();
  // Bumping this remounts the status bar (and its query) after a role switch.
  const [roleNonce, setRoleNonce] = useState(0);
  const basePath = `/investigations/${investigation.id}/analysis`;

  const value = useMemo(
    () => ({ investigation, refresh, basePath }),
    [investigation, refresh, basePath]
  );

  // 1–8 switch views, unless the analyst is typing or a modifier is held.
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = document.activeElement;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return;
      const n = Number(e.key);
      if (!Number.isInteger(n) || n < 1 || n > VIEWS.length) return;
      e.preventDefault();
      const view = VIEWS[n - 1];
      navigate(view.to ? `${basePath}/${view.to}` : basePath);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [basePath, navigate]);

  return (
    <AnalysisCaseContext.Provider value={value}>
      <div className="space-y-5">
        <Card className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-3 py-0 pr-3">
          <nav className="flex gap-5 overflow-x-auto scrollbar-thin" aria-label="Analysis views">
            {VIEWS.map((view, i) => (
              <NavLink
                key={view.to || 'overview'}
                to={view.to ? `${basePath}/${view.to}` : basePath}
                end={view.end}
                className={({ isActive }) =>
                  cn(
                    'group flex shrink-0 items-center gap-1.5 border-b-2 py-2.5 font-mono text-[11.5px] font-medium uppercase tracking-[0.08em] transition-colors duration-150',
                    isActive
                      ? 'border-accent text-accent'
                      : 'border-transparent text-navy-500 hover:text-navy-900'
                  )
                }
              >
                {view.label}
                <kbd
                  className="rounded-[3px] px-1 font-mono text-[9.5px] font-normal opacity-55"
                  style={{ background: 'var(--surface-sunken)' }}
                  aria-hidden
                >
                  {i + 1}
                </kbd>
              </NavLink>
            ))}
          </nav>

          {/* Live figures + the role every request is made as. */}
          <CaseStatusBar className="py-2" key={roleNonce} onRoleChange={() => setRoleNonce((n) => n + 1)} />
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
