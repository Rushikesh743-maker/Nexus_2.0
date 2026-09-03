import { cn } from '@/lib/utils';

/**
 * Tables.
 *
 * Dense but breathing: hairline row rules, a quiet sunken header, and figures
 * set in the mono face with tabular numerals so columns of scores, counts and
 * confidences align down the page. Rows are the primary reading surface in
 * this product, so they get the tightest attention.
 */
export function Table({ className, children, ...props }) {
  return (
    <div className="w-full overflow-x-auto scrollbar-thin">
      <table className={cn('w-full min-w-[640px] border-collapse text-left text-[13px]', className)} {...props}>
        {children}
      </table>
    </div>
  );
}

export function THead({ className, children }) {
  return <thead className={className}>{children}</thead>;
}

export function TBody({ className, children }) {
  return <tbody className={cn('divide-y divide-line-soft', className)}>{children}</tbody>;
}

export function Tr({ className, onClick, selected, children, ...props }) {
  const clickable = typeof onClick === 'function';
  return (
    <tr
      onClick={onClick}
      className={cn(
        'transition-colors duration-100',
        clickable && 'cursor-pointer hover:bg-slate-50',
        selected && 'bg-slate-50',
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
        'border-b border-line bg-slate-50 px-4 py-2 text-micro font-semibold uppercase text-navy-400',
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
    <td className={cn('px-4 py-2.5 align-middle text-navy-700', className)} {...props}>
      {children}
    </td>
  );
}
