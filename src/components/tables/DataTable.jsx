import { useEffect, useState } from 'react';
import { Card, CardBody } from '@/components/ui/Card';
import { Table, THead, TBody, Tr, Th, Td } from '@/components/ui/Table';
import { Skeleton } from '@/components/ui/LoadingState';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Pagination } from './Pagination';
import { cn } from '@/lib/utils';

/**
 * Generic table with loading / error / empty states and optional client-side
 * pagination.
 *
 * columns: [{ key, header, render?(row), className?, headerClassName? }]
 */
export function DataTable({
  columns,
  data = [],
  getRowId = (row) => row.id,
  isLoading = false,
  error,
  onRetry,
  onRowClick,
  selectedRowId,
  emptyIcon,
  emptyTitle = 'No records found',
  emptyDescription,
  emptyAction,
  paginated = true,
  pageSize = 8,
  bare = false,
  className,
}) {
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [data]);

  const totalPages = Math.max(1, Math.ceil(data.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visible = paginated ? data.slice((safePage - 1) * pageSize, safePage * pageSize) : data;

  const content = (
    <>
      {isLoading ? (
        <div className="space-y-3 p-4" role="status" aria-label="Loading records">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4">
              {columns.map((c) => (
                <Skeleton key={c.key} className={cn('h-4 flex-1', i % 2 ? 'opacity-80' : 'opacity-100')} />
              ))}
            </div>
          ))}
        </div>
      ) : error ? (
        <ErrorState compact title="Could not load records" description={error.message} onRetry={onRetry} />
      ) : visible.length === 0 ? (
        <EmptyState icon={emptyIcon} title={emptyTitle} description={emptyDescription} action={emptyAction} />
      ) : (
        <Table>
          <THead>
            <tr>
              {columns.map((col) => (
                <Th key={col.key} className={col.headerClassName}>
                  {col.header}
                </Th>
              ))}
            </tr>
          </THead>
          <TBody>
            {visible.map((row) => {
              const rowId = getRowId(row);
              return (
                <Tr key={rowId} onClick={onRowClick ? () => onRowClick(row) : undefined} selected={selectedRowId === rowId}>
                  {columns.map((col) => (
                    <Td key={col.key} className={col.className}>
                      {col.render ? col.render(row) : row[col.key]}
                    </Td>
                  ))}
                </Tr>
              );
            })}
          </TBody>
        </Table>
      )}
      {paginated && !isLoading && !error && data.length > 0 && (
        <Pagination page={safePage} totalPages={totalPages} total={data.length} pageSize={pageSize} onPageChange={setPage} />
      )}
    </>
  );

  if (bare) return <div className={className}>{content}</div>;

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardBody className="p-0">{content}</CardBody>
    </Card>
  );
}
