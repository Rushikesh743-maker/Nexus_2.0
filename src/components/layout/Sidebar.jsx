import { NavLink, Link, useLocation } from 'react-router-dom';
import { X, LogOut, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Logo } from '@/components/ui/Logo';
import { Tooltip } from '@/components/ui/Tooltip';
import { Avatar } from '@/components/ui/Avatar';
import { IconButton } from '@/components/ui/Button';
import { mainNav, caseNav, getActiveCaseId } from '@/lib/navigation';
import { useAuth } from '@/context/AuthContext';

function NavItem({ to, label, icon: Icon, end, collapsed, onClick }) {
  const link = (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          isActive ? 'bg-teal-50 text-teal-800' : 'text-navy-500 hover:bg-slate-100 hover:text-navy-800',
          collapsed && 'lg:justify-center lg:px-0'
        )
      }
    >
      <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
      <span className={cn('truncate', collapsed && 'lg:hidden')}>{label}</span>
    </NavLink>
  );
  if (!collapsed) return link;
  return (
    <Tooltip label={label} side="right" className="w-full">
      {link}
    </Tooltip>
  );
}

function SectionLabel({ children, collapsed }) {
  return (
    <p className={cn('px-3 pb-1.5 pt-4 text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300', collapsed && 'lg:hidden')}>
      {children}
    </p>
  );
}

function SidebarContent({ collapsed, onNavigate }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const caseId = getActiveCaseId(location.pathname);

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div className="flex h-full flex-col">
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4 scrollbar-thin" aria-label="Primary">
        <SectionLabel collapsed={collapsed}>Main</SectionLabel>
        {mainNav.map((item) => (
          <NavItem key={item.to} {...item} collapsed={collapsed} onClick={onNavigate} />
        ))}

        {caseId ? (
          <>
            <SectionLabel collapsed={collapsed}>Case workspace</SectionLabel>
            {caseNav.map((item) => (
              <NavItem
                key={item.label}
                to={`/investigations/${caseId}${item.to}`}
                label={item.label}
                icon={item.icon}
                end={item.end}
                collapsed={collapsed}
                onClick={onNavigate}
              />
            ))}
          </>
        ) : (
          !collapsed && (
            <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-3.5">
              <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                <p className="text-[11px] leading-relaxed text-navy-400">
                  Open an investigation to access evidence, network, map, timeline and intelligence tools.
                </p>
              </div>
            </div>
          )
        )}
      </nav>

      <div className="border-t border-slate-100 p-3">
        {collapsed ? (
          <div className="hidden flex-col items-center gap-2 lg:flex">
            <Tooltip label="Settings" side="right">
              <Link to="/settings" onClick={onNavigate} className="block rounded-full">
                <Avatar name={user?.name || ''} size="md" />
              </Link>
            </Tooltip>
            <IconButton icon={LogOut} label="Sign out" variant="ghost" size="iconSm" onClick={handleLogout} />
          </div>
        ) : (
          <div className="flex items-center gap-2.5">
            <Avatar name={user?.name || ''} size="md" />
            <div className="min-w-0 flex-1 lg:block">
              <p className="truncate text-[13px] font-semibold text-navy-800">{user?.name}</p>
              <p className="truncate text-[11px] text-navy-400">{user?.role}</p>
            </div>
            <IconButton icon={LogOut} label="Sign out" variant="ghost" size="iconSm" onClick={handleLogout} />
          </div>
        )}
        <Link
          to="/settings"
          onClick={onNavigate}
          className={cn(
            'mt-1 flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-navy-500 transition-colors hover:bg-slate-100 hover:text-navy-800',
            collapsed && 'lg:hidden'
          )}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px] shrink-0" aria-hidden>
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          Settings
        </Link>
      </div>
    </div>
  );
}

export function Sidebar({ collapsed, onToggleCollapse, mobileOpen, onCloseMobile }) {
  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-slate-200 bg-white transition-[width] duration-200 lg:flex',
          collapsed ? 'w-[76px]' : 'w-64'
        )}
      >
        <div className={cn('flex h-16 shrink-0 items-center border-b border-slate-100 px-5', collapsed && 'lg:justify-center lg:px-0')}>
          <Link to="/dashboard" aria-label="NEXUS home">
            <Logo compact={collapsed} />
          </Link>
        </div>
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="absolute -right-3.5 top-[68px] z-10 hidden h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-navy-400 shadow-sm transition-colors hover:text-navy-700 lg:flex"
        >
          {collapsed ? <PanelRightIcon /> : <PanelLeftIcon />}
        </button>
        <SidebarContent collapsed={collapsed} />
      </aside>

      {/* Mobile drawer */}
      <div className={cn('fixed inset-0 z-50 lg:hidden', !mobileOpen && 'pointer-events-none')}>
        <div
          className={cn('absolute inset-0 bg-navy-950/40 transition-opacity', mobileOpen ? 'opacity-100' : 'opacity-0')}
          onClick={onCloseMobile}
          aria-hidden
        />
        <aside
          className={cn(
            'absolute inset-y-0 left-0 flex w-72 flex-col border-r border-slate-200 bg-white transition-transform duration-200',
            mobileOpen ? 'translate-x-0' : '-translate-x-full'
          )}
          aria-label="Sidebar"
        >
          <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-100 px-5">
            <Link to="/dashboard" onClick={onCloseMobile}>
              <Logo />
            </Link>
            <IconButton icon={X} label="Close menu" onClick={onCloseMobile} />
          </div>
          <SidebarContent collapsed={false} onNavigate={onCloseMobile} />
        </aside>
      </div>
    </>
  );
}

function PanelLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

function PanelRightIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M15 3v18" />
    </svg>
  );
}
