import { Badge } from '@/components/ui/Badge';

/**
 * Compact entity chip for the case overview. `entity` is the v1 key-entity
 * row: { id, canonical_name, type, aliases, connection_count }.
 */
export function EntityChip({ entity, typeLabel }) {
  return (
    <li className="flex items-center gap-2.5 rounded-md border border-line bg-slate-50/60 px-3 py-2">
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-navy-800" title={entity.canonical_name}>
          {entity.canonical_name}
        </span>
        {entity.aliases?.length ? (
          <span className="block truncate text-[10.5px] text-navy-400" title={entity.aliases.join(', ')}>
            aka {entity.aliases.join(', ')}
          </span>
        ) : (
          <span className="block text-[10.5px] text-navy-300">{typeLabel}</span>
        )}
      </span>
      <Badge variant="neutral">{entity.connection_count ?? 0} links</Badge>
    </li>
  );
}
