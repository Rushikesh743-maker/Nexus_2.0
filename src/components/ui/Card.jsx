import { cn } from '@/lib/utils';

/**
 * Panels are defined by a hairline rule, not by elevation.
 *
 * Shadows are almost entirely removed: on a dense screen full of tables and
 * graphs, stacked drop shadows read as visual noise. Structure comes from
 * 1px rules and spacing, which is also what survives a dark ground.
 */
export function Card({ className, children, ...props }) {
  return (
    <div className={cn('rounded-lg border border-line bg-surface', className)} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, actions, className, children }) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-line-soft px-5 py-3.5',
        className
      )}
    >
      <div className="min-w-0">
        {title && <h2 className="text-[13.5px] font-semibold tracking-tight text-navy-900">{title}</h2>}
        {subtitle && <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-navy-400">{subtitle}</p>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ className, children, ...props }) {
  return (
    <div className={cn('px-5 py-4', className)} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({ className, children, ...props }) {
  return (
    <div className={cn('border-t border-line-soft bg-slate-50 px-5 py-3', className)} {...props}>
      {children}
    </div>
  );
}
