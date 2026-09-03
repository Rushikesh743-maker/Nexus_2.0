import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Search,
  Briefcase,
  Share2,
  FolderOpen,
  History,
  MapPin,
  Link2,
  LayoutDashboard,
  Settings,
  Plus,
  CornerDownLeft,
  Sun,
  Moon,
  Radar,
  SearchX,
} from 'lucide-react';
import { investigationService } from '@/services';
import { useTheme } from '@/context/ThemeContext';
import { Spinner } from '@/components/ui/LoadingState';
import { cn } from '@/lib/utils';

export const COMMAND_PALETTE_EVENT = 'nexus:command-palette';

/** Open the palette from anywhere (topbar button, empty states, shortcuts). */
export function openCommandPalette() {
  window.dispatchEvent(new Event(COMMAND_PALETTE_EVENT));
}

const RESULT_GROUPS = [
  { key: 'investigations', label: 'Investigations', icon: Briefcase },
  { key: 'entities', label: 'Entities', icon: Share2 },
  { key: 'evidence', label: 'Evidence', icon: FolderOpen },
  { key: 'events', label: 'Events', icon: History },
  { key: 'locations', label: 'Locations', icon: MapPin },
  { key: 'relationships', label: 'Relationships', icon: Link2 },
];

/**
 * Command palette — one place to go anywhere or find anything.
 *
 * This exists to flatten the navigation. Previously the sidebar repeated the
 * case tabs, so the same links lived in two places and the chrome grew a level
 * every time a surface was added. Now the sidebar carries only the top-level
 * sections, and everything deeper is one ⌘K away.
 */
export function CommandPalette() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark, toggle } = useTheme();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [cursor, setCursor] = useState(0);

  const inputRef = useRef(null);
  const listRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
    setResults(null);
    setCursor(0);
  }, []);

  const go = useCallback(
    (to) => {
      close();
      navigate(to);
    },
    [close, navigate]
  );

  /** Static destinations and actions, always available. */
  const commands = useMemo(() => {
    const caseMatch = location.pathname.match(/^\/investigations\/([^/]+)/);
    const caseId = caseMatch && caseMatch[1] !== 'new' ? caseMatch[1] : null;

    const global = [
      { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, hint: 'Overview', run: () => go('/dashboard') },
      { id: 'investigations', label: 'All investigations', icon: Briefcase, hint: 'Caseload', run: () => go('/investigations') },
      { id: 'new', label: 'New investigation', icon: Plus, hint: 'Create', run: () => go('/investigations/new') },
      { id: 'settings', label: 'Settings', icon: Settings, hint: 'Preferences', run: () => go('/settings') },
      {
        id: 'theme',
        label: isDark ? 'Switch to light theme' : 'Switch to dark theme',
        icon: isDark ? Sun : Moon,
        hint: 'Appearance',
        run: () => {
          toggle();
          close();
        },
      },
    ];

    if (!caseId) return global;

    const c = (path, label) => ({
      id: `case-${path || 'overview'}`,
      label,
      icon: Radar,
      hint: 'Current case',
      run: () => go(`/investigations/${caseId}${path}`),
    });

    /*
     * Inside a case, the case's own screens come first. The default list is
     * truncated, and an analyst who opened the palette from a case file is far
     * more likely to want a screen in it than the global dashboard.
     */
    return [
      c('', 'Case overview'),
      c('/evidence', 'Evidence'),
      c('/network', 'Network'),
      c('/timeline', 'Timeline'),
      c('/analysis', 'Network analysis'),
      c('/analysis/patterns', 'Suspicious patterns'),
      c('/analysis/people', 'Key people'),
      c('/analysis/links', 'Link analysis'),
      c('/analysis/ask', 'Ask a question'),
      c('/analysis/system', 'System'),
      ...global,
    ];
  }, [location.pathname, isDark, toggle, go, close]);

  const term = query.trim();

  const matchedCommands = useMemo(() => {
    if (!term) return commands.slice(0, 8);
    const q = term.toLowerCase();
    return commands.filter((c) => c.label.toLowerCase().includes(q)).slice(0, 6);
  }, [commands, term]);

  // Open/close via ⌘K, / and the custom event.
  useEffect(() => {
    const onKey = (e) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === 'Escape') setOpen(false);
      // "/" focuses search, unless the analyst is already typing somewhere.
      if (e.key === '/' && !open) {
        const el = document.activeElement;
        const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
        if (!typing) {
          e.preventDefault();
          setOpen(true);
        }
      }
    };
    const onEvent = () => setOpen(true);
    document.addEventListener('keydown', onKey);
    window.addEventListener(COMMAND_PALETTE_EVENT, onEvent);
    return () => {
      document.removeEventListener('keydown', onKey);
      window.removeEventListener(COMMAND_PALETTE_EVENT, onEvent);
    };
  }, [open]);

  // Lock the page and focus the field while open.
  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const t = setTimeout(() => inputRef.current?.focus(), 20);
    return () => {
      document.body.style.overflow = prev;
      clearTimeout(t);
    };
  }, [open]);

  // Debounced search across the mock stores.
  useEffect(() => {
    if (!open || term.length < 2) {
      setResults(null);
      setBusy(false);
      return undefined;
    }
    setBusy(true);
    let active = true;
    const t = setTimeout(() => {
      investigationService
        .globalSearch(term)
        .then((r) => active && (setResults(r), setBusy(false)))
        .catch(() => active && (setResults(null), setBusy(false)));
    }, 160);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [term, open]);

  /** Everything selectable, flattened, so one cursor walks the whole list. */
  const flat = useMemo(() => {
    const rows = matchedCommands.map((c) => ({ kind: 'command', run: c.run, key: c.id }));
    RESULT_GROUPS.forEach((g) => {
      (results?.[g.key] || []).slice(0, 5).forEach((item) => {
        rows.push({ kind: 'result', run: () => go(item.to), key: `${g.key}-${item.id || item.to}` });
      });
    });
    return rows;
  }, [matchedCommands, results, go]);

  useEffect(() => {
    setCursor(0);
  }, [term, results]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector(`[data-index="${cursor}"]`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [cursor, open]);

  function onKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setCursor((i) => (flat.length ? (i + 1) % flat.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setCursor((i) => (flat.length ? (i - 1 + flat.length) % flat.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      flat[cursor]?.run();
    }
  }

  if (!open) return null;

  let index = -1;
  const totalResults = results?.total ?? 0;

  return createPortal(
    <div className="fixed inset-0 z-[90]" role="dialog" aria-modal="true" aria-label="Command palette">
      <div
        className="animate-fade-in absolute inset-0 backdrop-blur-[2px]"
        style={{ background: 'var(--scrim)' }}
        onClick={close}
        aria-hidden
      />

      <div className="animate-rise absolute left-1/2 top-[12vh] w-[min(94vw,640px)] -translate-x-1/2">
        <div className="overflow-hidden rounded-xl border border-line bg-surface-raised shadow-overlay">
          {/* Field */}
          <div className="flex items-center gap-3 border-b border-line-soft px-4">
            {busy ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Search className="h-4 w-4 shrink-0 text-navy-300" aria-hidden />
            )}
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Search cases, entities, evidence — or jump to a page"
              aria-label="Search or jump to"
              className="h-14 flex-1 bg-transparent text-[15px] text-navy-900 outline-none placeholder:text-navy-300"
            />
            <kbd className="figure hidden shrink-0 rounded border border-line px-1.5 py-0.5 text-[10px] text-navy-400 sm:block">
              ESC
            </kbd>
          </div>

          {/* Rows */}
          <div ref={listRef} className="max-h-[52vh] overflow-y-auto scrollbar-thin py-2">
            {matchedCommands.length > 0 && (
              <div className="mb-1">
                <p className="label-micro px-4 pb-1 pt-1.5">{term ? 'Actions' : 'Jump to'}</p>
                {matchedCommands.map((c) => {
                  index += 1;
                  const i = index;
                  return (
                    <Row
                      key={c.id}
                      index={i}
                      active={cursor === i}
                      icon={c.icon}
                      label={c.label}
                      hint={c.hint}
                      onSelect={c.run}
                      onHover={() => setCursor(i)}
                    />
                  );
                })}
              </div>
            )}

            {RESULT_GROUPS.map((g) => {
              const items = (results?.[g.key] || []).slice(0, 5);
              if (!items.length) return null;
              return (
                <div key={g.key} className="mb-1">
                  <p className="label-micro px-4 pb-1 pt-1.5">{g.label}</p>
                  {items.map((item) => {
                    index += 1;
                    const i = index;
                    return (
                      <Row
                        key={`${g.key}-${item.id || item.to}`}
                        index={i}
                        active={cursor === i}
                        icon={g.icon}
                        label={item.label}
                        hint={item.sub}
                        onSelect={() => go(item.to)}
                        onHover={() => setCursor(i)}
                      />
                    );
                  })}
                </div>
              );
            })}

            {term.length >= 2 && !busy && totalResults === 0 && matchedCommands.length === 0 && (
              <div className="flex flex-col items-center px-6 py-10 text-center">
                <SearchX className="h-5 w-5 text-navy-300" aria-hidden />
                <p className="mt-2.5 text-[13px] font-medium text-navy-700">No match for “{term}”</p>
                <p className="mt-0.5 text-[12px] text-navy-400">
                  Search covers cases, entities, evidence, events, locations and relationships.
                </p>
              </div>
            )}
          </div>

          {/* Footer legend */}
          <div className="flex items-center gap-4 border-t border-line-soft bg-slate-50 px-4 py-2">
            <Legend keys={['↑', '↓']} label="Navigate" />
            <Legend keys={[<CornerDownLeft key="e" className="h-3 w-3" aria-hidden />]} label="Open" />
            <Legend keys={['ESC']} label="Close" />
            <span className="ml-auto text-[11px] text-navy-300">
              {totalResults > 0 ? `${totalResults} match${totalResults === 1 ? '' : 'es'}` : 'NEXUS'}
            </span>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

function Row({ index, active, icon: Icon, label, hint, onSelect, onHover }) {
  return (
    <button
      type="button"
      data-index={index}
      onMouseMove={onHover}
      onClick={onSelect}
      className={cn(
        'flex w-full items-center gap-3 px-4 py-2 text-left transition-colors',
        active ? 'bg-slate-50' : 'hover:bg-slate-50'
      )}
    >
      <Icon
        className={cn('h-3.5 w-3.5 shrink-0', active ? 'text-navy-700' : 'text-navy-300')}
        aria-hidden
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium text-navy-800">{label}</span>
        {hint && <span className="block truncate text-[11px] text-navy-400">{hint}</span>}
      </span>
      {active && <CornerDownLeft className="h-3 w-3 shrink-0 text-navy-300" aria-hidden />}
    </button>
  );
}

function Legend({ keys, label }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-navy-400">
      {keys.map((k, i) => (
        <kbd
          key={i}
          className="figure inline-flex h-4 min-w-4 items-center justify-center rounded border border-line px-1 text-[10px] text-navy-500"
        >
          {k}
        </kbd>
      ))}
      {label}
    </span>
  );
}
