import { AlertTriangle, RotateCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './Button';

export function ErrorState({ title = 'Something went wrong', description, onRetry, action, compact = false, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 text-center', compact ? 'py-8' : 'py-14', className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50">
        <AlertTriangle className="h-5 w-5 text-rose-500" aria-hidden />
      </div>
      <h3 className="mt-3.5 text-sm font-semibold text-navy-800">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-navy-400">{description}</p>}
      {(onRetry || action) && (
        <div className="mt-4 flex items-center gap-2">
          {onRetry && (
            <Button variant="outline" size="sm" icon={RotateCw} onClick={onRetry}>
              Try again
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}
