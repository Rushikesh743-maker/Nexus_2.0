import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Logo } from './Logo';

export function Spinner({ className }) {
  return <Loader2 className={cn('h-5 w-5 animate-spin text-teal-600', className)} aria-label="Loading" />;
}

export function PageLoader({ label = 'Loading…', full = false }) {
  return (
    <div className={cn('flex min-h-[50vh] flex-col items-center justify-center gap-3', full && 'min-h-screen')}>
      <Logo compact />
      <div className="flex items-center gap-2 text-[13px] text-navy-400">
        <Spinner className="h-4 w-4" />
        {label}
      </div>
    </div>
  );
}

export function Skeleton({ className }) {
  return <div className={cn('animate-pulse rounded-md bg-slate-200/80', className)} aria-hidden />;
}
