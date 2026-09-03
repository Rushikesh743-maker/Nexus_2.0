import { useState } from 'react';
import { Card, CardBody } from '@/components/ui/Card';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { cn } from '@/lib/utils';

/**
 * Horizontal bar list — the reference console's primary way of showing a small
 * ranked distribution.
 *
 * Every one of these carries a TABLE toggle, because a value that is only
 * reachable by reading a bar length is a value an investigator cannot quote.
 * The bars are proportional to the largest row, and the figure is always
 * printed alongside rather than inferred from the bar.
 */
export function BarRowsPanel({
  title,
  caption,
  rows = [],
  valueLabel = 'Count',
  color = 'var(--accent)',
  renderLabel,
  onRowClick,
  className,
}) {
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(...rows.map((r) => Number(r.value) || 0), 1);

  return (
    <Card className={className}>
      <div className="flex items-start justify-between gap-4 border-b border-line-soft px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="font-mono text-[11.5px] font-semibold uppercase tracking-[0.09em] text-navy-900">
            {title}
          </h2>
          {caption && <p className="mt-1 text-[11.5px] text-navy-400">{caption}</p>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          aria-pressed={asTable}
          className={cn(
            'shrink-0 font-mono text-[10px] uppercase tracking-[0.1em] transition-colors',
            asTable ? 'text-accent' : 'text-navy-400 hover:text-navy-800'
          )}
        >
          {asTable ? 'Chart' : 'Table'}
        </button>
      </div>

      <CardBody className={asTable ? 'p-0' : undefined}>
        {rows.length === 0 ? (
          <p className="py-6 text-center text-[12.5px] text-navy-400">Nothing to show.</p>
        ) : asTable ? (
          <Table className="min-w-0">
            <THead>
              <Tr>
                <Th>Item</Th>
                <Th className="w-28 text-right">{valueLabel}</Th>
              </Tr>
            </THead>
            <TBody>
              {rows.map((r) => (
                <Tr key={r.key} onClick={onRowClick ? () => onRowClick(r) : undefined}>
                  <Td>{r.label}</Td>
                  <Td className="figure text-right font-semibold">{r.value}</Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => {
              const pct = ((Number(r.value) || 0) / max) * 100;
              const Row = onRowClick ? 'button' : 'div';
              return (
                <li key={r.key}>
                  <Row
                    {...(onRowClick
                      ? { type: 'button', onClick: () => onRowClick(r) }
                      : {})}
                    className={cn(
                      'flex w-full items-center gap-3 rounded px-1 py-[3px] text-left',
                      onRowClick && 'transition-colors hover:bg-slate-50'
                    )}
                  >
                    <span className="w-[132px] shrink-0 truncate text-[12.5px] text-navy-700">
                      {renderLabel ? renderLabel(r) : r.label}
                    </span>
                    <span className="h-[9px] min-w-0 flex-1 overflow-hidden rounded-[2px] bg-slate-50">
                      <span
                        className="block h-full rounded-[2px] transition-[width] duration-300 ease-instrument"
                        style={{ width: `${Math.max(pct, 2)}%`, background: r.color || color }}
                      />
                    </span>
                    <span className="figure w-8 shrink-0 text-right text-[12px] font-semibold text-navy-800">
                      {r.value}
                    </span>
                  </Row>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

/** Section heading in the console's register: uppercase mono, wide-tracked. */
export function PanelTitle({ children, className }) {
  return (
    <h2
      className={cn(
        'font-mono text-[11.5px] font-semibold uppercase tracking-[0.09em] text-navy-900',
        className
      )}
    >
      {children}
    </h2>
  );
}
