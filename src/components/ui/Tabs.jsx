import { cn } from '@/lib/utils';

/**
 * Segmented tab control.
 *
 * The active segment is a solid ink block rather than a raised white chip —
 * consistent with the sidebar and buttons, and unambiguous on either ground.
 */
export function Tabs({ tabs = [], value, onChange, className }) {
  return (
    <div
      className={cn('inline-flex flex-wrap items-center gap-0.5 rounded-md border border-line p-0.5', className)}
      role="tablist"
    >
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange?.(tab.id)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[12.5px] font-medium transition-colors duration-150',
              active
                ? 'bg-surface-inverse text-action-on'
                : 'text-navy-500 hover:bg-slate-50 hover:text-navy-900'
            )}
          >
            {tab.icon && <tab.icon className="h-3.5 w-3.5" aria-hidden />}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
