import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Briefcase, Share2, FolderOpen, X, SearchX, ArrowRight, History, MapPin, Link2 } from 'lucide-react';
import { investigationService } from '@/services';
import { Spinner } from '@/components/ui/LoadingState';
import { cn } from '@/lib/utils';

const GROUPS = [
  { key: 'investigations', label: 'Investigations', icon: Briefcase },
  { key: 'entities', label: 'Entities', icon: Share2 },
  { key: 'evidence', label: 'Evidence', icon: FolderOpen },
  { key: 'events', label: 'Events', icon: History },
  { key: 'locations', label: 'Locations', icon: MapPin },
  { key: 'relationships', label: 'Relationships', icon: Link2 },
];

/**
 * Global search across investigations, entities and evidence — frontend
 * filtering via investigationService.globalSearch() (mock data today,
 * backend /search endpoint tomorrow).
 * variant: 'bar' (inline input + dropdown, desktop) | 'overlay' (mobile).
 */
export function GlobalSearch({ variant = 'bar', autoFocus = false, onNavigate }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const inputRef = useRef(null);

  // Debounced search.
  useEffect(() => {
    if (!open) return undefined;
    const term = query.trim();
    if (term.length < 2) {
      setResults(null);
      setBusy(false);
      return undefined;
    }
    setBusy(true);
    let active = true;
    const t = setTimeout(() => {
      investigationService
        .globalSearch(term)
        .then((r) => {
          if (!active) return;
          setResults(r);
          setBusy(false);
        })
        .catch(() => {
          if (!active) return;
          setResults({ investigations: [], entities: [], evidence: [], events: [], locations: [], relationships: [], total: 0 });
          setBusy(false);
        });
    }, 180);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [query, open]);

  // Outside click + Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const goTo = (item) => {
    setOpen(false);
    setQuery('');
    setResults(null);
    onNavigate?.();
    navigate(item.to);
  };

  const showPanel = open && query.trim().length >= 2;
  const hasResults = results && results.total > 0;

  const panel = showPanel && (
    <div
      className={cn(
        'animate-fade-in overflow-hidden rounded-xl border border-slate-200 bg-white shadow-dropdown',
        variant === 'bar' ? 'absolute left-0 right-0 top-full z-50 mt-2' : ''
      )}
      role="listbox"
      aria-label="Search results"
    >
      {busy && !results ? (
        <div className="flex items-center gap-2 px-4 py-4 text-[13px] text-navy-400">
          <Spinner className="h-4 w-4" /> Searching…
        </div>
      ) : !hasResults ? (
        <div className="flex flex-col items-center gap-1.5 px-4 py-7 text-center">
          <SearchX className="h-5 w-5 text-navy-200" aria-hidden />
          <p className="text-[13px] font-medium text-navy-600">No matches for “{query.trim()}”</p>
          <p className="text-[12px] text-navy-300">Try a case code, entity name, alias or evidence reference.</p>
        </div>
      ) : (
        <div className="max-h-[420px] overflow-y-auto scrollbar-thin">
          {GROUPS.map((group) => {
            const items = results[group.key];
            if (!items || items.length === 0) return null;
            return (
              <div key={group.key} className="border-b border-slate-100 last:border-b-0">
                <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-300">
                  {group.label}
                </p>
                <ul className="pb-1.5">
                  {items.map((item) => (
                    <li key={`${group.key}-${item.id}`}>
                      <button
                        type="button"
                        onClick={() => goTo(item)}
                        className="flex w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-slate-50"
                      >
                        <group.icon className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-navy-700">{item.label}</span>
                          <span className="block truncate text-[11px] text-navy-300">{item.sub}</span>
                        </span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-navy-200" aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onNavigate?.();
              navigate(`/investigations?q=${encodeURIComponent(query.trim())}`);
            }}
            className="flex w-full items-center justify-center gap-1.5 border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-[12px] font-medium text-teal-700 transition-colors hover:bg-slate-100"
          >
            See all matching investigations
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      )}
    </div>
  );

  if (variant === 'overlay') {
    return (
      <div className="fixed inset-0 z-[70] flex flex-col bg-white" role="dialog" aria-label="Search">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3" ref={wrapRef}>
          <Search className="h-4 w-4 shrink-0 text-navy-300" aria-hidden />
          <input
            ref={inputRef}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search investigations, entities, evidence…"
            aria-label="Search investigations, entities, evidence"
            className="h-9 flex-1 bg-transparent text-sm text-navy-800 placeholder:text-navy-300 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onNavigate?.();
            }}
            aria-label="Close search"
            className="rounded-md p-1.5 text-navy-400 hover:bg-slate-100"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">{showPanel && panel}</div>
        {!showPanel && (
          <p className="px-6 pb-8 text-center text-[12px] leading-relaxed text-navy-300">
            Search covers case titles and codes, entity names and aliases, and evidence references — all data stays on this
            device in the demo build.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="relative" ref={wrapRef}>
      <Search className="pointer-events-none absolute left-3 top-1/2 z-[1] h-4 w-4 -translate-y-1/2 text-navy-300" aria-hidden />
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search investigations, entities, evidence…"
        aria-label="Search investigations, entities, evidence"
        className="h-9 w-64 rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-8 text-sm text-navy-800 placeholder:text-navy-300 transition-colors focus:border-teal-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-500/30 lg:w-80"
      />
      {query && (
        <button
          type="button"
          onClick={() => {
            setQuery('');
            inputRef.current?.focus();
          }}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 z-[1] -translate-y-1/2 rounded p-1 text-navy-300 hover:text-navy-600"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}
      {panel}
    </div>
  );
}
