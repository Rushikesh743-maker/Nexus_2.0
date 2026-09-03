import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';

/*
 * The icon tile is deliberately monochrome. A stat card's colour would be
 * decoration, and colour in this product is reserved for meaning — the figure
 * itself is the signal here.
 */
const TILE = 'bg-slate-50 text-navy-500';

export function StatCard({ icon: Icon, label, value, sub, to, className }) {
  const body = (
    <Card
      className={cn(
        'flex items-start gap-3.5 p-4 transition-colors',
        to && 'hover:border-line-strong',
        className
      )}
    >
      {Icon && (
        <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-md', TILE)}>
          <Icon className="h-4 w-4" aria-hidden />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="label-micro leading-[1.4]">{label}</p>
        <p className="figure mt-1.5 text-[26px] font-semibold leading-none tracking-tight text-navy-900">
          {value ?? '—'}
        </p>
        {sub && <p className="mt-1.5 text-[11.5px] leading-snug text-navy-400">{sub}</p>}
      </div>
      {to && <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />}
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
