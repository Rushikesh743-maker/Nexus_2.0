import { cn } from '@/lib/utils';

export function Table({ className, children, ...props }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn('w-full min-w-[640px] border-collapse text-left text-sm', className)} {...props}>
        {children}
      </table>
    </div>
  );
}

export function THead({ className, children }) {
  return <thead className={className}>{children}</thead>;
}

export function TBody({ className, children }) {
  return <tbody className={cn('divide-y divide-slate-100', className)}>{children}</tbody>;
}

export function Tr({ className, onClick, selected, children, ...props }) {
  const clickable = typeof onClick === 'function';
  return (
    <tr
      onClick={onClick}
      className={cn(
        clickable && 'cursor-pointer transition-colors hover:bg-slate-50',
        selected && 'bg-teal-50/50',
        className
      )}
      {...props}
    >
      {children}
    </tr>
  );
}

export function Th({ className, children, ...props }) {
  return (
    <th
      className={cn(
        'border-b border-slate-200 bg-slate-50/80 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-navy-400',
        className
      )}
      {...props}
    >
      {children}
    </th>
  );
}

export function Td({ className, children, ...props }) {
  return (
    <td className={cn('px-4 py-3 align-middle text-navy-700', className)} {...props}>
      {children}
    </td>
  );
}
