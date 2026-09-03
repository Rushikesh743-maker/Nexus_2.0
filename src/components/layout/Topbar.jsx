import { Link, useLocation } from 'react-router-dom';
import { Menu, Bell, Search, Sparkles, ChevronRight } from 'lucide-react';
import { IconButton } from '@/components/ui/Button';
import { Dropdown } from '@/components/ui/Dropdown';
import { ThemeToggleButton } from '@/components/ui/ThemeToggle';
import { NotificationsDropdown } from './NotificationsDropdown';
import { DEMO_TOUR_EVENT } from '@/components/demo/DemoModeTour';
import { openCommandPalette } from './CommandPalette';
import { UserMenu } from './UserMenu';
import { getPageContext } from '@/lib/navigation';
import { cn } from '@/lib/utils';

/** Where you are, as a short trail rather than a single word. */
function Trail() {
  const location = useLocation();
  const { title, caseId } = getPageContext(location.pathname);

  const crumbs = [];
  if (caseId) {
    crumbs.push({ label: 'Investigations', to: '/investigations' });
    const rest = location.pathname.split('/').slice(3).filter(Boolean);
    const section = rest[0];
    const sub = rest[1];
    crumbs.push({ label: 'Case file', to: `/investigations/${caseId}` });
    if (section) crumbs.push({ label: section.replace(/-/g, ' ') });
    if (sub) crumbs.push({ label: sub.replace(/-/g, ' ') });
  } else {
    crumbs.push({ label: title });
  }

  return (
    <nav className="flex min-w-0 items-center gap-1.5" aria-label="Breadcrumb">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={i} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && <ChevronRight className="h-3 w-3 shrink-0 text-navy-200" aria-hidden />}
            {c.to && !last ? (
              <Link
                to={c.to}
                className="truncate text-[12.5px] text-navy-400 transition-colors hover:text-navy-800"
              >
                {c.label}
              </Link>
            ) : (
              <span
                className={cn(
                  'truncate text-[12.5px] capitalize',
                  last ? 'font-medium text-navy-800' : 'text-navy-400'
                )}
              >
                {c.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

/**
 * Top bar.
 *
 * The inline search field is gone: search and navigation now share one command
 * palette, so this bar carries a single trigger instead of a field that only
 * did half the job. What is left is location, then the small set of controls
 * that apply everywhere.
 */
export function Topbar({ onMenu }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md">
      <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
        <IconButton icon={Menu} label="Open menu" onClick={onMenu} className="lg:hidden" />

        <Trail />

        <div className="ml-auto flex items-center gap-2">
          {/* One trigger for search *and* navigation. */}
          <button
            type="button"
            onClick={openCommandPalette}
            className="group hidden h-8 items-center gap-2 rounded-md border border-line bg-slate-50 pl-2.5 pr-2 text-navy-400 transition-colors hover:border-line-strong hover:text-navy-700 md:flex"
            aria-label="Search or jump to"
          >
            <Search className="h-3.5 w-3.5" aria-hidden />
            <span className="text-[12.5px]">Search…</span>
            <kbd className="figure ml-6 rounded border border-line px-1.5 py-px text-[10px] text-navy-400">
              ⌘K
            </kbd>
          </button>

          <IconButton
            icon={Search}
            label="Search"
            variant="outline"
            className="md:hidden"
            onClick={openCommandPalette}
          />

          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event(DEMO_TOUR_EVENT))}
            className="hidden h-8 items-center gap-1.5 rounded-md border border-line px-2.5 text-[12px] font-medium text-navy-500 transition-colors hover:border-line-strong hover:text-navy-900 sm:flex"
            title="Guided walkthrough"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Demo
          </button>

          <ThemeToggleButton />

          <Dropdown width={316} trigger={<IconButton icon={Bell} label="Notifications" variant="outline" />}>
            <NotificationsDropdown />
          </Dropdown>

          <UserMenu />
        </div>
      </div>
    </header>
  );
}
