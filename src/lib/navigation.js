import { matchPath } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
  FolderKanban,
  Bot,
  FileText,
  FolderOpen,
  Network,
  Map as MapIcon,
  History,
  Lightbulb,
  ClipboardList,
  Layers,
} from 'lucide-react';

/** Primary, always-visible navigation. */
export const mainNav = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/cases', label: 'Cases', icon: FolderKanban, end: true },
  { to: '/investigations', label: 'Investigations', icon: Briefcase, end: false },
  { to: '/copilot', label: 'Copilot', icon: Bot, end: true },
];

/** Sub-navigation shown while an analysis investigation is open. */
export const caseNav = [
  { to: '', label: 'Overview', icon: FileText, end: true },
  { to: '/workspace', label: 'Workspace', icon: Layers },
  { to: '/evidence', label: 'Evidence', icon: FolderOpen },
  { to: '/network', label: 'Network', icon: Network },
  { to: '/map', label: 'Map', icon: MapIcon },
  { to: '/timeline', label: 'Timeline', icon: History },
  { to: '/intelligence', label: 'Intelligence', icon: Lightbulb },
  { to: '/reports', label: 'Reports', icon: ClipboardList },
];

/**
 * Tool tabs inside a live case file (/cases/:caseId). Rendered by the case
 * layout, never by the sidebar — the sidebar answers "where in the app am I",
 * the case answers "where in the case am I".
 */
export const v1CaseTabs = [
  { to: '', label: 'Overview', end: true },
  { to: 'documents', label: 'Documents' },
  { to: 'entities', label: 'Entities' },
  { to: 'relationships', label: 'Relationships' },
  { to: 'graph', label: 'Graph' },
  { to: 'timeline', label: 'Timeline' },
  { to: 'map', label: 'Map' },
  { to: 'evidence', label: 'Evidence' },
  { to: 'investigation', label: 'Intelligence' },
  { to: 'hypotheses', label: 'Hypotheses' },
  { to: 'contradictions', label: 'Contradictions' },
  { to: 'gaps', label: 'Gaps' },
  { to: 'impact', label: 'Impact' },
  { to: 'simulation', label: 'Simulation' },
  { to: 'copilot', label: 'Copilot' },
  { to: 'reports', label: 'Reports' },
  { to: 'snapshots', label: 'Snapshots' },
  { to: 'review', label: 'Review' },
];

/**
 * Resolve the current section for the top bar.
 *
 * Returns { title, caseId?, caseBase? } — caseBase is the path prefix of the
 * open case file ('/investigations/:id' or '/cases/:id') so the breadcrumb
 * trail can point at the right registry.
 */
export function getPageContext(pathname) {
  if (matchPath('/investigations/new', pathname)) return { title: 'New investigation' };

  const v1Case =
    matchPath('/cases/:id/*', pathname) || matchPath('/cases/:id', pathname);
  if (v1Case) {
    return { title: 'Case file', caseId: v1Case.params.id, caseBase: '/cases' };
  }

  const caseMatch =
    matchPath('/investigations/:id/*', pathname) || matchPath('/investigations/:id', pathname);
  if (caseMatch && caseMatch.params.id !== 'new') {
    return { title: 'Case file', caseId: caseMatch.params.id, caseBase: '/investigations' };
  }
  if (pathname.startsWith('/dashboard')) return { title: 'Dashboard' };
  if (pathname.startsWith('/cases')) return { title: 'Cases' };
  if (pathname.startsWith('/investigations')) return { title: 'Investigations' };
  if (pathname.startsWith('/copilot')) return { title: 'Copilot' };
  if (pathname.startsWith('/settings')) return { title: 'Settings' };
  return { title: 'NEXUS' };
}

/** Match an active investigation id from a path, if any. */
export function getActiveCaseId(pathname) {
  const match =
    matchPath('/investigations/:id/*', pathname) || matchPath('/investigations/:id', pathname);
  const id = match?.params.id;
  return id && id !== 'new' ? id : null;
}

/** The live platform case id when the path is under /cases/:caseId. */
export function getActiveV1CaseId(pathname) {
  const match =
    matchPath('/cases/:id/*', pathname) || matchPath('/cases/:id', pathname);
  return match?.params.id || null;
}
