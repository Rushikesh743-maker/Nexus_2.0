import { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { ENTITY_TYPES, ENTITY_RESOLUTION } from '@/lib/constants';
import { cn, truncate } from '@/lib/utils';

/**
 * Custom React Flow node.
 * - Distinct accent per entity type (NEXUS palette), dashed style for
 *   evidence records.
 * - Neutral identity-resolution dot (never a risk/criminality label).
 * - `dimmed` / `highlighted` support highlight modes and search.
 */
const EntityNode = memo(({ data }) => {
  const { entity, dimmed, highlighted } = data;
  const isEvidence = entity.type === 'evidence';
  const typeMeta = isEvidence
    ? { label: 'Evidence', color: '#64748b' }
    : ENTITY_TYPES[entity.type] || ENTITY_TYPES.asset;
  const color = typeMeta.color;
  const resolution = ENTITY_RESOLUTION[entity.resolution] || ENTITY_RESOLUTION.unverified;

  return (
    <div
      className={cn(
        'nf-node w-[178px] rounded-xl border bg-white p-3 transition-opacity',
        isEvidence ? 'border-dashed' : 'border-slate-200',
        highlighted ? 'border-teal-500 shadow-md ring-2 ring-teal-500/50' : 'shadow-card hover:shadow-md',
        dimmed ? 'opacity-20' : 'opacity-100'
      )}
      style={{ borderTop: `3px solid ${color}` }}
    >
      <Handle type="target" position={Position.Top} className="!invisible" />
      <div className="flex items-center gap-2.5">
        <span
          style={{ backgroundColor: `${color}1f`, color }}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold"
        >
          {isEvidence ? 'EV' : typeMeta.label.slice(0, 2).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12.5px] font-semibold leading-tight text-navy-800" title={entity.name}>
            {truncate(entity.name, 26)}
          </p>
          <p className="mt-0.5 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-navy-300">
            {typeMeta.label}
            {!isEvidence && entity.connections > 0 && (
              <span className="rounded bg-slate-100 px-1 font-semibold normal-case text-navy-400">
                {entity.connections} links
              </span>
            )}
          </p>
        </div>
        {!isEvidence && (
          <span
            className="h-2 w-2 shrink-0 rounded-full ring-2 ring-white"
            style={{ backgroundColor: resolution.color || '#94a3b8' }}
            title={`Resolution: ${resolution.label}`}
          />
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!invisible" />
    </div>
  );
});

EntityNode.displayName = 'EntityNode';
export default EntityNode;
