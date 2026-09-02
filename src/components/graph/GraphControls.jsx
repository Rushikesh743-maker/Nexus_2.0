import { Search, Expand, Shrink, RotateCcw, Maximize2, Eye } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { ENTITY_TYPES, RELATIONSHIP_TYPES } from '@/lib/constants';
import { cn } from '@/lib/utils';

const TYPE_CHIPS = [
  { id: 'all', label: 'All' },
  { id: 'person', label: 'Person' },
  { id: 'vehicle', label: 'Vehicle' },
  { id: 'phone_number', label: 'Phone' },
  { id: 'address', label: 'Location' },
  { id: 'organization', label: 'Organization' },
  { id: 'bank_account', label: 'Account' },
];

const REL_OPTIONS = [
  { value: 'all', label: 'All relationships' },
  ...Object.entries(RELATIONSHIP_TYPES).map(([value, meta]) => ({ value, label: meta.label })),
];

const DATE_OPTIONS = [
  { value: 'all', label: 'Any activity date' },
  { value: '7', label: 'Active in last 7 days' },
  { value: '30', label: 'Active in last 30 days' },
  { value: '90', label: 'Active in last 90 days' },
];

/**
 * Network graph control bar: search, type/relationship/date filters,
 * evidence-node toggle, structural highlight modes and graph actions
 * (expand / hide connections on the selected node, reset, fit).
 */
export function GraphControls({
  search,
  onSearch,
  typeFilter,
  onTypeFilter,
  relFilter,
  onRelFilter,
  dateFilter,
  onDateFilter,
  includeEvidence,
  onIncludeEvidence,
  insights,
  highlightMode,
  onHighlightMode,
  hasSelection,
  onExpand,
  onHide,
  onReset,
  onFit,
  compact = false,
}) {
  const highlightChips = [
    { id: 'hubs', label: 'High-connectivity', count: insights?.hubs?.length || 0 },
    { id: 'bridges', label: 'Potential bridge entity', count: insights?.bridges?.length || 0 },
    { id: 'crossCase', label: 'Cross-case connection', count: insights?.crossCase?.length || 0 },
    ...(insights?.clusters || []).map((c) => ({ id: `cluster:${c.id}`, label: c.label, count: c.entityIds.length })),
  ];
  const highlightsAvailable =
    Boolean(onHighlightMode) &&
    (insights?.hubs?.length || insights?.bridges?.length || insights?.crossCase?.length || (insights?.clusters || []).length) > 0;

  return (
    <div className="space-y-3 border-b border-slate-100 px-4 py-3">
      <div className={cn('flex flex-wrap items-center gap-2', compact && 'gap-1.5')}>
        <div className={compact ? 'w-44' : 'w-52'}>
          <Input icon={Search} placeholder="Search entity…" aria-label="Search entity in graph" value={search} onChange={(e) => onSearch(e.target.value)} />
        </div>
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Filter by entity type">
          {TYPE_CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => onTypeFilter(chip.id)}
              aria-pressed={typeFilter === chip.id}
              className={cn(
                'rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
                typeFilter === chip.id
                  ? 'border-navy-700 bg-navy-800 text-white'
                  : 'border-slate-200 bg-white text-navy-500 hover:border-navy-300'
              )}
            >
              {chip.label}
            </button>
          ))}
        </div>
        {!compact && (
          <>
            <div className="w-44">
              <Select value={relFilter} onChange={(e) => onRelFilter(e.target.value)} options={REL_OPTIONS} aria-label="Filter by relationship" />
            </div>
            <div className="w-44">
              <Select value={dateFilter} onChange={(e) => onDateFilter(e.target.value)} options={DATE_OPTIONS} aria-label="Filter by activity date" />
            </div>
          </>
        )}
        <button
          type="button"
          onClick={() => onIncludeEvidence(!includeEvidence)}
          aria-pressed={includeEvidence}
          className={cn(
            'ml-auto flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium transition-colors',
            includeEvidence
              ? 'border-teal-500 bg-teal-50 text-teal-800'
              : 'border-slate-200 bg-white text-navy-500 hover:border-teal-300'
          )}
        >
          <FileIcon />
          Include evidence files
        </button>
      </div>

      <div className={cn('flex flex-wrap items-center gap-1.5', !highlightsAvailable && 'hidden')}>
        <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-300">
          <Eye className="h-3 w-3" aria-hidden /> Highlight
        </span>
        {highlightChips.map((chip) => (
          <button
            key={chip.id}
            type="button"
            onClick={() => onHighlightMode(highlightMode === chip.id ? null : chip.id)}
            aria-pressed={highlightMode === chip.id}
            className={cn(
              'rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
              highlightMode === chip.id
                ? 'border-teal-600 bg-teal-600 text-white'
                : 'border-slate-200 bg-white text-navy-500 hover:border-teal-300'
            )}
          >
            {chip.label} <span className="opacity-60">{chip.count}</span>
          </button>
        ))}

        <span className="ml-auto flex items-center gap-1.5">
          <Button variant="outline" size="sm" icon={Expand} disabled={!hasSelection} onClick={onExpand}>
            Expand connections
          </Button>
          <Button variant="outline" size="sm" icon={Shrink} disabled={!hasSelection} onClick={onHide}>
            Hide connections
          </Button>
          <Button variant="ghost" size="sm" icon={RotateCcw} onClick={onReset}>
            Reset view
          </Button>
          <Button variant="ghost" size="sm" icon={Maximize2} onClick={onFit}>
            Fit graph
          </Button>
        </span>
      </div>
    </div>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5" aria-hidden>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </svg>
  );
}
