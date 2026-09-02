import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { DemoModeTour } from '@/components/demo/DemoModeTour';
import { APP_VERSION } from '@/lib/constants';
import { storage } from '@/lib/storage';
import { cn } from '@/lib/utils';

const SIDEBAR_KEY = 'nexus.sidebar';

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => storage.getItem(SIDEBAR_KEY) === 'collapsed');
  const location = useLocation();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      storage.setItem(SIDEBAR_KEY, prev ? 'expanded' : 'collapsed');
      return !prev;
    });
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={toggleCollapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className={cn('flex min-h-screen flex-col transition-[padding] duration-200', collapsed ? 'lg:pl-[76px]' : 'lg:pl-64')}>
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
        <footer className="border-t border-slate-200 px-4 py-3 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-2 text-[11px] text-navy-300">
            <span>
              NEXUS {APP_VERSION} — frontend preview · fictional demo data only
            </span>
            <span>NEXUS provides analytical assistance and investigation leads. It does not determine guilt or replace investigator judgment.</span>
          </div>
        </footer>
      </div>

      <DemoModeTour />
    </div>
  );
}
