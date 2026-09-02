import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export function Pagination({ page, totalPages, total, pageSize, onPageChange }) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-2.5">
      <p className="text-xs text-navy-400">
        Showing <span className="font-medium text-navy-600">{from}–{to}</span> of{' '}
        <span className="font-medium text-navy-600">{total}</span>
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded-md border border-slate-200 bg-white p-1.5 text-navy-500 shadow-sm transition-colors hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-40"
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
        </button>
        <span className="px-1.5 text-xs font-medium text-navy-500">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className={cn('rounded-md border border-slate-200 bg-white p-1.5 text-navy-500 shadow-sm transition-colors hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-40')}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}
