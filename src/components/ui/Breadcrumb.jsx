import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

/** items: [{ label, to? }] — last item is the current page. */
export function Breadcrumb({ items = [], className }) {
  if (!items.length) return null;
  return (
    <nav aria-label="Breadcrumb" className={cn('flex flex-wrap items-center gap-1 text-[12px]', className)}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={`${item.label}-${i}`} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3 w-3 text-navy-200" aria-hidden />}
            {item.to && !isLast ? (
              <Link to={item.to} className="font-medium text-navy-400 transition-colors hover:text-teal-700">
                {item.label}
              </Link>
            ) : (
              <span className={cn(isLast ? 'font-medium text-navy-700' : 'text-navy-400')}>{item.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
