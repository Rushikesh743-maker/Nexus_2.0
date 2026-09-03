import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Search, Eye, FolderOpen, Network, Archive, RotateCcw, LayoutGrid, List, X, SearchX, Radar } from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { Button, IconButton, buttonClasses } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { DataTable } from '@/components/tables/DataTable';
import { InvestigationCard } from '@/components/cards/InvestigationCard';
import { Dropdown, DropdownItem, DropdownDivider } from '@/components/ui/Dropdown';
import { ConfirmDialog } from '@/components/modals/ConfirmDialog';
import { MoreHorizontal } from 'lucide-react';
import { investigationService } from '@/services';
import { INVESTIGATION_STATUS, PRIORITY } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { cn, timeAgo } from '@/lib/utils';

const STATUS_COLORS = {
  active: 'var(--data-teal)',
  pending_review: 'var(--data-amber)',
  closed: 'var(--ink-400)',
  archived: 'var(--ink-300)',
};

const statusOptions = [
  { value: 'all', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'pending_review', label: 'Under review' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
];

const priorityOptions = [
  { value: 'all', label: 'All priorities' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

/** One filter chip. Active state is a solid ink block, as elsewhere. */
function FilterChip({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] font-medium transition-colors duration-150',
        active
          ? 'border-transparent bg-surface-inverse text-action-on'
          : 'border-line text-navy-500 hover:border-line-strong hover:text-navy-900'
      )}
    >
      {children}
    </button>
  );
}

export function InvestigationsPage() {
  useDocumentTitle('Investigations');
  const navigate = useNavigate();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [view, setView] = useState('table');

  const q = searchParams.get('q') || '';
  const status = searchParams.get('status') || 'all';
  const priority = searchParams.get('priority') || 'all';

  const [inputValue, setInputValue] = useState(q);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(null);
  const [confirmArchive, setConfirmArchive] = useState(null);
  const [archiving, setArchiving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  // Keep local input in sync when the URL query changes (e.g. topbar search).
  useEffect(() => {
    setInputValue(q);
  }, [q]);

  // Debounced fetch.
  useEffect(() => {
    let active = true;
    setBusy(true);
    const t = setTimeout(() => {
      investigationService
        .list({ search: q, status, priority })
        .then((r) => {
          if (!active) return;
          setResult(r);
          setError(null);
          setBusy(false);
        })
        .catch((e) => {
          if (!active) return;
          setError(e);
          setBusy(false);
        });
    }, 180);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [q, status, priority, reloadKey]);

  const setParam = useCallback(
    (key, value, defaultValue) => {
      const next = new URLSearchParams(searchParams);
      if (!value || value === defaultValue) next.delete(key);
      else next.set(key, value);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const handleArchive = async () => {
    if (!confirmArchive) return;
    setArchiving(true);
    try {
      const nextStatus = confirmArchive.status === 'archived' ? 'active' : 'archived';
      await investigationService.update(confirmArchive.id, { status: nextStatus });
      toast.success(nextStatus === 'archived' ? 'Investigation archived' : 'Investigation restored', confirmArchive.code);
      setReloadKey((k) => k + 1);
    } catch (e) {
      toast.error('Could not update investigation', e.message);
    } finally {
      setArchiving(false);
      setConfirmArchive(null);
    }
  };

  const columns = [
    {
      key: 'case',
      header: 'Case',
      render: (inv) => (
        <div className="flex items-center gap-3">
          <Avatar name={inv.lead?.name || '?'} size="sm" ring />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="shrink-0 rounded bg-navy-50 px-1.5 py-0.5 font-mono text-[11px] font-medium text-navy-500">
                {inv.code}
              </span>
              <span className="truncate text-[13px] font-semibold text-navy-800">{inv.title}</span>
            </div>
            <p className="mt-0.5 truncate text-[11px] text-navy-400">
              {inv.caseTypeLabel} · {inv.jurisdiction || '—'}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (inv) => {
        const meta = INVESTIGATION_STATUS[inv.status] || INVESTIGATION_STATUS.closed;
        return (
          <Badge variant={meta.variant} dot>
            {meta.label}
          </Badge>
        );
      },
    },
    {
      key: 'priority',
      header: 'Priority',
      render: (inv) => {
        const meta = PRIORITY[inv.priority] || PRIORITY.low;
        return <Badge variant={meta.variant}>{meta.label}</Badge>;
      },
    },
    { key: 'lead', header: 'Lead', render: (inv) => <span className="text-[13px]">{inv.lead?.name || 'Unassigned'}</span> },
    {
      key: 'stats',
      header: 'Case data',
      /*
       * An analysis-backed case holds no rows in the mock stores — its records
       * live in the pipeline — so counting them here reported "0 entities · 0
       * evidence · 0 events" for the fullest case in the product. Say where the
       * data actually is instead of printing zeros that are not true.
       */
      render: (inv) =>
        inv.analysisBackend === 'cna' ? (
          <Badge variant="teal">
            <Radar className="h-3 w-3" aria-hidden />
            Live pipeline
          </Badge>
        ) : (
          <span className="text-[12px] text-navy-400">
            {inv.stats.entities} entities · {inv.stats.evidence} evidence · {inv.stats.events} events
          </span>
        ),
    },
    { key: 'updated', header: 'Updated', className: 'text-right', render: (inv) => <span className="text-[12px] text-navy-400">{timeAgo(inv.updatedAt)}</span> },
    {
      key: 'actions',
      header: '',
      headerClassName: 'w-12',
      render: (inv) => (
        <div onClick={(e) => e.stopPropagation()} className="text-right">
          <Dropdown
            trigger={<IconButton icon={MoreHorizontal} label={`Actions for ${inv.code}`} />}
          >
            <DropdownItem icon={Eye} label="Open case" onClick={() => navigate(`/investigations/${inv.id}`)} />
            <DropdownItem icon={FolderOpen} label="Evidence" onClick={() => navigate(`/investigations/${inv.id}/evidence`)} />
            <DropdownItem icon={Network} label="Network" onClick={() => navigate(`/investigations/${inv.id}/network`)} />
            <DropdownDivider />
            <DropdownItem
              icon={inv.status === 'archived' ? RotateCcw : Archive}
              label={inv.status === 'archived' ? 'Restore' : 'Archive'}
              onClick={() => setConfirmArchive(inv)}
            />
          </Dropdown>
        </div>
      ),
    },
  ];

  const counts = result?.counts || { active: 0, pending_review: 0, closed: 0, archived: 0 };
  const items = result?.items || [];
  // `total` is the filtered count; `totalAll` is the whole caseload behind the
  // "All" chip, which must not change as filters narrow the list.
  const total = result?.total ?? items.length;
  const totalAll = Object.values(counts).reduce((a, b) => a + b, 0);
  const hasFilters = q || status !== 'all' || priority !== 'all';

  return (
    <div className="space-y-5">
      <PageHeader
        title="Investigations"
        description="All case files visible to your unit. Open a case to work its evidence, network and timeline."
        actions={
          <>
            <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm">
              <button
                type="button"
                onClick={() => setView('table')}
                aria-label="Table view"
                className={cn('rounded-md p-1.5 transition-colors', view === 'table' ? 'bg-navy-50 text-navy-700' : 'text-navy-300 hover:text-navy-600')}
              >
                <List className="h-4 w-4" aria-hidden />
              </button>
              <button
                type="button"
                onClick={() => setView('grid')}
                aria-label="Grid view"
                className={cn('rounded-md p-1.5 transition-colors', view === 'grid' ? 'bg-navy-50 text-navy-700' : 'text-navy-300 hover:text-navy-600')}
              >
                <LayoutGrid className="h-4 w-4" aria-hidden />
              </button>
            </div>
            <Link to="/investigations/new" className={buttonClasses('primary', 'md')}>
              <Plus className="mr-1.5 h-4 w-4" aria-hidden />
              New investigation
            </Link>
          </>
        }
      />

      {/*
        One filter row.

        Status was previously settable from both a chip row and a dropdown on
        the same screen — two controls for one piece of state, which is a way
        to make a page feel unpredictable. Priority is now a chip row too, so
        filtering is one click and consistent, and the counts live on the
        controls that set them.
      */}
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="w-full sm:w-72">
              <Input
                icon={Search}
                placeholder="Search title, code, tag…"
                aria-label="Search investigations"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setParam('q', inputValue, '');
                  if (e.key === 'Escape') {
                    setInputValue('');
                    setParam('q', '', '');
                  }
                }}
                onBlur={() => setParam('q', inputValue, '')}
              />
            </div>
            <span className="text-[12px] text-navy-400">
              {busy ? 'Loading…' : `${items.length} of ${total} case${total === 1 ? '' : 's'}`}
            </span>
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                icon={X}
                className="ml-auto"
                onClick={() => {
                  setInputValue('');
                  setSearchParams({}, { replace: true });
                }}
              >
                Clear filters
              </Button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="label-micro mr-1">Status</span>
              <FilterChip active={status === 'all'} onClick={() => setParam('status', 'all', 'all')}>
                All <span className="figure opacity-60">{totalAll}</span>
              </FilterChip>
              {Object.entries(INVESTIGATION_STATUS).map(([key, meta]) => (
                <FilterChip key={key} active={status === key} onClick={() => setParam('status', key, 'all')}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
                  {meta.label} <span className="figure opacity-60">{counts[key] ?? 0}</span>
                </FilterChip>
              ))}
            </span>

            <span className="flex flex-wrap items-center gap-1.5">
              <span className="label-micro mr-1">Priority</span>
              <FilterChip active={priority === 'all'} onClick={() => setParam('priority', 'all', 'all')}>
                Any
              </FilterChip>
              {Object.entries(PRIORITY).map(([key, meta]) => (
                <FilterChip key={key} active={priority === key} onClick={() => setParam('priority', key, 'all')}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
                  {meta.label}
                </FilterChip>
              ))}
            </span>
          </div>
        </CardBody>
      </Card>

      <div>
        <div>
          {view === 'table' ? (
            <DataTable
              columns={columns}
              data={items}
              isLoading={busy}
              error={error}
              onRetry={() => setReloadKey((k) => k + 1)}
              onRowClick={(inv) => navigate(`/investigations/${inv.id}`)}
              emptyIcon={SearchX}
              emptyTitle={hasFilters ? 'No investigations match these filters' : 'No investigations yet.'}
              emptyDescription={
                hasFilters
                  ? 'Adjust the search term or clear the filters to see the full caseload.'
                  : 'Create an investigation and upload evidence to begin analysis.'
              }
              emptyAction={
                !hasFilters && (
                  <Link to="/investigations/new" className={buttonClasses('primary', 'sm')}>
                    <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
                    New investigation
                  </Link>
                )
              }
              pageSize={8}
            />
          ) : (
            <div className="space-y-4">
              {busy ? (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Card key={i} className="h-40 animate-pulse" />
                  ))}
                </div>
              ) : items.length === 0 ? (
                <Card>
                  <CardBody>
                    <p className="py-8 text-center text-sm text-navy-400">No investigations match these filters.</p>
                  </CardBody>
                </Card>
              ) : (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {items.map((inv) => (
                    <InvestigationCard key={inv.id} investigation={inv} onClick={() => navigate(`/investigations/${inv.id}`)} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

      </div>

      <ConfirmDialog
        open={Boolean(confirmArchive)}
        onClose={() => setConfirmArchive(null)}
        onConfirm={handleArchive}
        loading={archiving}
        tone={confirmArchive?.status === 'archived' ? 'primary' : 'danger'}
        title={confirmArchive?.status === 'archived' ? 'Restore investigation' : 'Archive investigation'}
        message={
          confirmArchive?.status === 'archived'
            ? `Restore ${confirmArchive?.code} to active? It will reappear in the active caseload.`
            : `Archive ${confirmArchive?.code}? Archived cases stay searchable but leave the active caseload.`
        }
        confirmLabel={confirmArchive?.status === 'archived' ? 'Restore' : 'Archive'}
      />
    </div>
  );
}
