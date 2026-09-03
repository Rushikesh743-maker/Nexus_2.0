import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette } from './CommandPalette';
import { SyntheticBanner } from './SyntheticBanner';
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
    <div className="nexus-grain min-h-screen bg-ground">
      <SyntheticBanner />

      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={toggleCollapsed}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div
        className={cn(
          'relative z-[1] flex min-h-screen flex-col transition-[padding] duration-200 ease-instrument',
          collapsed ? 'lg:pl-[68px]' : 'lg:pl-[232px]'
        )}
      >
        <Topbar onMenu={() => setMobileOpen(true)} />

        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>

        <footer className="border-t border-line-soft px-4 py-4 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-x-6 gap-y-2">
            <span className="text-[11px] text-navy-300">
              NEXUS <span className="figure">{APP_VERSION}</span> · fictional demo data only
            </span>
            <span className="max-w-xl text-[11px] leading-relaxed text-navy-300">
              NEXUS provides analytical assistance and investigation leads. It does not determine guilt or replace
              investigator judgment.
            </span>
          </div>
        </footer>
      </div>

      <CommandPalette />
      <DemoModeTour />
    </div>
  );
}
