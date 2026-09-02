import { matchPath } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
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
  { to: '/investigations', label: 'Investigations', icon: Briefcase, end: false },
];

/** Sub-navigation shown while an investigation is open. */
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

/** Resolve the current section for the top bar. */
export function getPageContext(pathname) {
  if (matchPath('/investigations/new', pathname)) return { title: 'New investigation' };
  const caseMatch =
    matchPath('/investigations/:id/*', pathname) || matchPath('/investigations/:id', pathname);
  if (caseMatch && caseMatch.params.id !== 'new') {
    return { title: 'Case file', caseId: caseMatch.params.id };
  }
  if (pathname.startsWith('/dashboard')) return { title: 'Dashboard' };
  if (pathname.startsWith('/investigations')) return { title: 'Investigations' };
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
