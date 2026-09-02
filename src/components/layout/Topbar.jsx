import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Menu, Bell, Search, Sparkles } from 'lucide-react';
import { IconButton } from '@/components/ui/Button';
import { Dropdown, DropdownLabel } from '@/components/ui/Dropdown';
import { NotificationsDropdown } from './NotificationsDropdown';
import { DEMO_TOUR_EVENT } from '@/components/demo/DemoModeTour';
import { GlobalSearch } from './GlobalSearch';
import { UserMenu } from './UserMenu';
import { getPageContext } from '@/lib/navigation';

export function Topbar({ onMenu }) {
  const location = useLocation();
  const [searchOpen, setSearchOpen] = useState(false);
  const { title } = getPageContext(location.pathname);

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
        <IconButton icon={Menu} label="Open menu" onClick={onMenu} className="lg:hidden" />
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-navy-800">{title}</h2>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* Global search — inline on desktop, overlay on mobile */}
          <div className="hidden md:block">
            <GlobalSearch variant="bar" />
          </div>
          <IconButton
            icon={Search}
            label="Search"
            variant="outline"
            className="border-slate-200 shadow-none md:hidden"
            onClick={() => setSearchOpen(true)}
          />

          <Dropdown
            width={316}
            trigger={<IconButton icon={Bell} label="Notifications" variant="outline" className="border-slate-200 shadow-none" />}
          >
            <NotificationsDropdown />
          </Dropdown>

          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event(DEMO_TOUR_EVENT))}
            className="hidden items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-2 text-[12px] font-medium text-teal-800 transition-colors hover:bg-teal-100 sm:flex"
            title="Guided 3-minute walkthrough"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Demo Mode
          </button>

          <UserMenu />
        </div>
      </div>
      {searchOpen && (
        <GlobalSearch variant="overlay" autoFocus onNavigate={() => setSearchOpen(false)} />
      )}
    </header>
  );
}
