import { cn } from '@/lib/utils';

const SIDES = {
  top: 'bottom-full left-1/2 mb-1.5 -translate-x-1/2',
  bottom: 'top-full left-1/2 mt-1.5 -translate-x-1/2',
  left: 'right-full top-1/2 mr-1.5 -translate-y-1/2',
  right: 'left-full top-1/2 ml-1.5 -translate-y-1/2',
};

/** Lightweight CSS-only tooltip via group-hover. */
export function Tooltip({ label, side = 'right', className, children }) {
  if (!label) return children;
  return (
    <span className={cn('group/tt relative inline-flex', className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          'pointer-events-none absolute z-[70] whitespace-nowrap rounded-md bg-navy-900 px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-md transition-opacity duration-150 group-hover/tt:opacity-100',
          SIDES[side] || SIDES.right
        )}
      >
        {label}
      </span>
    </span>
  );
}
