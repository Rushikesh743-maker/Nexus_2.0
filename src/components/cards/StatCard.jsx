import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';

const TONES = {
  teal: 'bg-teal-50 text-teal-700',
  navy: 'bg-navy-50 text-navy-700',
  amber: 'bg-amber-50 text-amber-700',
  rose: 'bg-rose-50 text-rose-700',
  sky: 'bg-sky-50 text-sky-700',
  violet: 'bg-violet-50 text-violet-700',
};

export function StatCard({ icon: Icon, label, value, sub, tone = 'teal', to, className }) {
  const body = (
    <Card className={cn('flex items-center gap-4 p-4 transition-shadow', to && 'hover:shadow-md', className)}>
      {Icon && (
        <div className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-lg', TONES[tone] || TONES.teal)}>
          <Icon className="h-5 w-5" aria-hidden />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium uppercase tracking-wide text-navy-400">{label}</p>
        <p className="mt-0.5 text-2xl font-semibold leading-none text-navy-900">{value ?? '—'}</p>
        {sub && <p className="mt-1 truncate text-xs text-navy-400">{sub}</p>}
      </div>
      {to && <ChevronRight className="h-4 w-4 shrink-0 text-navy-200" aria-hidden />}
    </Card>
  );

  if (to) {
    return (
      <Link to={to} className="block focus-visible:rounded-xl">
        {body}
      </Link>
    );
  }
  return body;
}
