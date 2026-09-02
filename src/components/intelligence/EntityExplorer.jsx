import { useMemo, useState } from 'react';
import { Search, Users } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/EmptyState';
import { EntityCard } from '@/components/cards/EntityCard';
import { ENTITY_TYPES } from '@/lib/constants';
import { cn } from '@/lib/utils';

/** Explorer filter chips in spec order (type groups). */
const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'person', label: 'Person', match: ['person'] },
  { id: 'vehicle', label: 'Vehicle', match: ['vehicle'] },
  { id: 'phone', label: 'Phone', match: ['phone_number'] },
  { id: 'location', label: 'Location', match: ['address'] },
  { id: 'organization', label: 'Organization', match: ['organization'] },
  { id: 'account', label: 'Account', match: ['bank_account'] },
];

/**
 * Entity Explorer panel — search + type filters + entity cards.
 * entities are enriched records from intelligenceService.getNetwork().
 */
export function EntityExplorer({ entities = [], selectedId, onSelect, className }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  const filtered = useMemo(() => {
    const group = FILTERS.find((f) => f.id === filter);
    const term = query.trim().toLowerCase();
    return entities.filter((entity) => {
      if (group && group.match && !group.match.includes(entity.type)) return false;
      if (!term) return true;
      return [entity.name, ...(entity.aliases || []), entity.role, entity.notes || '']
        .join(' ')
        .toLowerCase()
        .includes(term);
    });
  }, [entities, filter, query]);

  return (
    <Card className={className}>
      <CardHeader
        title="Entities"
        subtitle={`${entities.length} tracked in this investigation · click a card for details`}
      />
      <CardBody className="space-y-3.5">
        <div className="sm:w-72">
          <Input
            icon={Search}
            placeholder="Search entities…"
            aria-label="Search entities"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter entities by type">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              aria-pressed={filter === f.id}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                filter === f.id
                  ? 'border-navy-700 bg-navy-800 text-white'
                  : 'border-slate-200 bg-white text-navy-500 hover:border-navy-300'
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            compact
            icon={Users}
            title={entities.length === 0 ? 'No entities tracked yet' : 'No entities match'}
            description={
              entities.length === 0
                ? 'Entities appear here as the ingestion pipeline processes evidence.'
                : 'Adjust the search term or type filter.'
            }
          />
        ) : (
          <div className="grid max-h-[430px] grid-cols-1 gap-3 overflow-y-auto pr-1 scrollbar-thin sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map((entity) => (
              <EntityCard key={entity.id} entity={entity} selected={selectedId === entity.id} onClick={onSelect} />
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
