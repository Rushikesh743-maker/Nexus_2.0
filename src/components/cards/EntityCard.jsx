import { ArrowRight } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ENTITY_TYPES, ENTITY_RESOLUTION } from '@/lib/constants';
import { cn } from '@/lib/utils';

/**
 * Entity explorer card — name, type, connection/evidence/event counts,
 * identity resolution and confidence, with an Explore action.
 * Neutral by design: no risk or criminality labels.
 */
export function EntityCard({ entity, onClick, selected = false, className }) {
  const typeMeta = ENTITY_TYPES[entity.type] || ENTITY_TYPES.asset;
  const TypeIcon = typeMeta.icon;
  const resolution = ENTITY_RESOLUTION[entity.resolution] || ENTITY_RESOLUTION.unverified;

  return (
    <Card
      onClick={() => onClick?.(entity)}
      className={cn(
        'flex h-full cursor-pointer flex-col p-3.5 transition-shadow',
        selected ? 'ring-2 ring-teal-500' : 'hover:shadow-md',
        className
      )}
    >
      <div className="flex items-start gap-3">
        <span
          style={{ backgroundColor: `${typeMeta.color}1a`, color: typeMeta.color }}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
        >
          <TypeIcon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13.5px] font-semibold text-navy-800" title={entity.name}>
            {entity.name}
          </p>
          <p className="text-[11px] text-navy-400">{typeMeta.label}</p>
        </div>
        <Badge variant={resolution.variant} dot>
          {resolution.label}
        </Badge>
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-50/80 px-2.5 py-2 text-center">
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wide text-navy-300">Connections</dt>
          <dd className="text-[15px] font-semibold text-navy-800">{entity.connections ?? 0}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wide text-navy-300">Evidence</dt>
          <dd className="text-[15px] font-semibold text-navy-800">{entity.evidenceCount ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-[10px] font-medium uppercase tracking-wide text-navy-300">Events</dt>
          <dd className="text-[15px] font-semibold text-navy-800">{entity.eventsCount ?? 0}</dd>
        </div>
      </dl>

      <div className="mt-2.5 flex items-center justify-between gap-2">
        <span className="text-[11px] text-navy-400">
          Resolution: <span className="font-medium text-navy-600">{resolution.label}</span>
          {entity.resolutionConfidence !== null && entity.resolutionConfidence !== undefined && (
            <span className="text-navy-300"> · {entity.resolutionConfidence}%</span>
          )}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onClick?.(entity);
          }}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-[11.5px] font-medium text-navy-700 shadow-sm transition-colors hover:border-teal-400 hover:bg-teal-50 hover:text-teal-800"
        >
          Explore
          <ArrowRight className="h-3 w-3" aria-hidden />
        </button>
      </div>
    </Card>
  );
}
