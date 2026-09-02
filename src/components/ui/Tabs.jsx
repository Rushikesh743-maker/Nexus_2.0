import { cn } from '@/lib/utils';

/** Segmented tab control. */
export function Tabs({ tabs = [], value, onChange, className }) {
  return (
    <div className={cn('inline-flex flex-wrap items-center gap-1 rounded-lg bg-slate-100 p-1', className)} role="tablist">
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
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
              active ? 'bg-white text-navy-900 shadow-sm' : 'text-navy-500 hover:text-navy-800'
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
