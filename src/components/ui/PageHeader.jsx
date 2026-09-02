import { cn } from '@/lib/utils';
import { Breadcrumb } from './Breadcrumb';

export function PageHeader({ breadcrumb, title, description, actions, className, children }) {
  return (
    <header className={cn('space-y-1', className)}>
      {breadcrumb && <Breadcrumb items={breadcrumb} className="mb-2" />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-navy-900">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-navy-400">{description}</p>}
          {children}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
