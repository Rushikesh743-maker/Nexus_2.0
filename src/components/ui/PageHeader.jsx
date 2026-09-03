import { cn } from '@/lib/utils';
import { Breadcrumb } from './Breadcrumb';

/**
 * Page header.
 *
 * The title is set in the display serif — the one place the editorial voice
 * appears. It gives each screen a clear entry point without spending colour,
 * and it is what stops a near-monochrome interface reading as undesigned.
 */
export function PageHeader({ breadcrumb, title, description, actions, className, children }) {
  return (
    <header className={cn('space-y-1', className)}>
      {breadcrumb && <Breadcrumb items={breadcrumb} className="mb-2.5" />}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="font-display text-[26px] leading-[1.15] text-navy-900">{title}</h1>
          {description && (
            <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-navy-400">{description}</p>
          )}
          {children}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
