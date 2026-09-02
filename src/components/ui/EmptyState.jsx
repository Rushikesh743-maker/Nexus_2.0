import { FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils';

export function EmptyState({
  icon: Icon = FolderOpen,
  title = 'Nothing here yet',
  description,
  action,
  compact = false,
  className,
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 text-center', compact ? 'py-8' : 'py-14', className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
        <Icon className="h-5 w-5 text-navy-300" aria-hidden />
      </div>
      <h3 className="mt-3.5 text-sm font-semibold text-navy-800">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-navy-400">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
