import { Link, NavLink, useLocation } from 'react-router-dom';
import { X, LogOut, Settings, Plus, ChevronLeft, ChevronRight, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Logo } from '@/components/ui/Logo';
import { Tooltip } from '@/components/ui/Tooltip';
import { Avatar } from '@/components/ui/Avatar';
import { IconButton } from '@/components/ui/Button';
import { mainNav, getActiveCaseId } from '@/lib/navigation';
import { useAuth } from '@/context/AuthContext';
import { investigationService } from '@/services';
import { useEffect, useState } from 'react';

/**
 * A single primary destination.
 *
 * The active state is a solid ink block rather than a tinted pill: under the
 * design thesis colour belongs to data, so "where am I" is signalled by
 * contrast. A 2px marker on the leading edge carries the same information for
 * anyone who cannot separate the two fills.
 */
function NavItem({ to, label, icon: Icon, end, collapsed, onClick }) {
  const link = (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          'group relative flex w-full items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium',
          'transition-[background-color,color,transform] duration-150 ease-instrument active:scale-[0.98]',
          isActive
            ? 'bg-surface-inverse text-action-on shadow-glow'
            : 'text-navy-500 hover:bg-slate-50 hover:text-navy-900',
          collapsed && 'lg:justify-center lg:px-0'
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-accent transition-all duration-200"
              aria-hidden
            />
          )}
          <Icon className="h-4 w-4 shrink-0 transition-transform duration-150 group-hover:scale-110" aria-hidden />
          <span className={cn('truncate', collapsed && 'lg:hidden')}>{label}</span>
        </>
      )}
    </NavLink>
  );

  if (!collapsed) return link;
  return (
    <Tooltip label={label} side="right" className="w-full">
      {link}
    </Tooltip>
  );
}

/**
 * The case currently open, shown as context rather than as a second menu.
 *
 * The previous sidebar repeated every case tab here, so the same eight links
 * existed in two places at once. The tabs inside the case file already do that
 * job; this only answers "which case am I in", and gets out of the way.
 */
function CaseContext({ caseId, collapsed, onNavigate }) {
  const [record, setRecord] = useState(null);

  useEffect(() => {
    let active = true;
    investigationService
      .getById(caseId)
      .then((r) => active && setRecord(r))
      .catch(() => active && setRecord(null));
    return () => {
      active = false;
    };
  }, [caseId]);

  if (collapsed) {
    return (
      <div className="hidden justify-center px-3 pt-3 lg:flex">
        <Tooltip label={record?.title || 'Open case'} side="right">
          <Link
            to={`/investigations/${caseId}`}
            onClick={onNavigate}
            className="figure flex h-8 w-8 items-center justify-center rounded-md border border-line text-[10px] font-semibold text-navy-600 transition-colors hover:border-line-strong hover:text-navy-900"
          >
            {record?.code?.split('-').pop() || '··'}
          </Link>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className="px-3 pt-4">
      <p className="label-micro px-1 pb-1.5">Open case</p>
      <Link
        to={`/investigations/${caseId}`}
        onClick={onNavigate}
        className="group block rounded-md border border-line bg-slate-50 px-3 py-2.5 transition-colors hover:border-line-strong"
      >
        <span className="flex items-center justify-between gap-2">
          <span className="figure text-[11px] text-navy-400">{record?.code || '—'}</span>
          <ArrowUpRight
            className="h-3 w-3 shrink-0 text-navy-300 transition-colors group-hover:text-navy-600"
            aria-hidden
          />
        </span>
        <span className="mt-1 block truncate text-[12.5px] font-medium leading-snug text-navy-800">
          {record?.title || 'Loading…'}
        </span>
      </Link>
    </div>
  );
}

function SidebarBody({ collapsed, onNavigate }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const caseId = getActiveCaseId(location.pathname);

  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-4" aria-label="Primary">
        <div className="space-y-0.5">
          {mainNav.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} onClick={onNavigate} />
          ))}
        </div>

        {/* Creating a case is the one action that belongs in primary nav. */}
        <div className="mt-2">
          {collapsed ? (
            <Tooltip label="New investigation" side="right" className="w-full">
              <NavLink
                to="/investigations/new"
                onClick={onNavigate}
                className="hidden w-full justify-center rounded-md border border-dashed border-line-strong py-2 text-navy-400 transition-colors hover:border-navy-400 hover:text-navy-800 lg:flex"
              >
                <Plus className="h-4 w-4" aria-hidden />
              </NavLink>
            </Tooltip>
          ) : (
            <NavLink
              to="/investigations/new"
              onClick={onNavigate}
              className="flex items-center gap-3 rounded-md border border-dashed border-line-strong px-3 py-2 text-[13px] font-medium text-navy-400 transition-colors hover:border-navy-400 hover:text-navy-800"
            >
              <Plus className="h-4 w-4 shrink-0" aria-hidden />
              New investigation
            </NavLink>
          )}
        </div>

        {caseId && <CaseContext caseId={caseId} collapsed={collapsed} onNavigate={onNavigate} />}
      </nav>

      {/* Account */}
      <div className="border-t border-line-soft p-3">
        {collapsed ? (
          <div className="hidden flex-col items-center gap-1.5 lg:flex">
            <Tooltip label={user?.name || 'Account'} side="right">
              <Link to="/settings" onClick={onNavigate} className="block rounded-full">
                <Avatar name={user?.name || ''} size="sm" />
              </Link>
            </Tooltip>
            <Tooltip label="Settings" side="right">
              <Link
                to="/settings"
                onClick={onNavigate}
                className="flex h-7 w-7 items-center justify-center rounded-md text-navy-400 transition-colors hover:bg-slate-50 hover:text-navy-800"
              >
                <Settings className="h-3.5 w-3.5" aria-hidden />
              </Link>
            </Tooltip>
            <IconButton icon={LogOut} label="Sign out" variant="ghost" size="iconSm" onClick={logout} />
          </div>
        ) : (
          <>
            <Link
              to="/settings"
              onClick={onNavigate}
              className="flex items-center gap-2.5 rounded-md px-2 py-2 transition-colors hover:bg-slate-50"
            >
              <Avatar name={user?.name || ''} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-medium text-navy-800">{user?.name}</span>
                <span className="block truncate text-[11px] text-navy-400">{user?.role}</span>
              </span>
              <Settings className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
            </Link>
            <button
              type="button"
              onClick={logout}
              className="mt-0.5 flex w-full items-center gap-3 rounded-md px-2 py-2 text-[12.5px] font-medium text-navy-400 transition-colors hover:bg-slate-50 hover:text-navy-800"
            >
              <LogOut className="h-4 w-4 shrink-0" aria-hidden />
              Sign out
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function Sidebar({ collapsed, onToggleCollapse, mobileOpen, onCloseMobile }) {
  return (
    <>
      {/* Desktop rail */}
      <aside
        className={cn(
          'fixed bottom-0 left-0 top-[27px] z-40 hidden flex-col border-r border-line bg-surface transition-[width] duration-200 ease-instrument lg:flex',
          collapsed ? 'w-[68px]' : 'w-[232px]'
        )}
      >
        <div
          className={cn(
            'flex h-14 shrink-0 items-center border-b border-line-soft px-4',
            collapsed && 'lg:justify-center lg:px-0'
          )}
        >
          <Link to="/dashboard" aria-label="NEXUS home">
            <Logo compact={collapsed} />
          </Link>
        </div>

        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="absolute -right-3 top-16 z-10 hidden h-6 w-6 items-center justify-center rounded-full border border-line bg-surface text-navy-400 transition-colors hover:border-line-strong hover:text-navy-800 lg:flex"
        >
          {collapsed ? (
            <ChevronRight className="h-3 w-3" aria-hidden />
          ) : (
            <ChevronLeft className="h-3 w-3" aria-hidden />
          )}
        </button>

        <SidebarBody collapsed={collapsed} />
      </aside>

      {/* Mobile drawer */}
      <div className={cn('fixed inset-0 z-50 lg:hidden', !mobileOpen && 'pointer-events-none')}>
        <div
          className={cn('absolute inset-0 transition-opacity', mobileOpen ? 'opacity-100' : 'opacity-0')}
          style={{ background: 'var(--scrim)' }}
          onClick={onCloseMobile}
          aria-hidden
        />
        <aside
          className={cn(
            'absolute inset-y-0 left-0 flex w-[264px] flex-col border-r border-line bg-surface transition-transform duration-200 ease-instrument',
            mobileOpen ? 'translate-x-0' : '-translate-x-full'
          )}
          aria-label="Sidebar"
        >
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-line-soft px-4">
            <Link to="/dashboard" onClick={onCloseMobile}>
              <Logo />
            </Link>
            <IconButton icon={X} label="Close menu" onClick={onCloseMobile} />
          </div>
          <SidebarBody collapsed={false} onNavigate={onCloseMobile} />
        </aside>
      </div>
    </>
  );
}
