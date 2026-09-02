import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Search, Eye, FolderOpen, Network, Archive, RotateCcw, LayoutGrid, List, X, SearchX } from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { Button, IconButton, buttonClasses } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DataTable } from '@/components/tables/DataTable';
import { InvestigationCard } from '@/components/cards/InvestigationCard';
import { StatusDonut } from '@/components/charts/StatusDonut';
import { ChartCard } from '@/components/charts/ChartCard';
import { Dropdown, DropdownItem, DropdownDivider } from '@/components/ui/Dropdown';
import { ConfirmDialog } from '@/components/modals/ConfirmDialog';
import { MoreHorizontal } from 'lucide-react';
import { investigationService } from '@/services';
import { INVESTIGATION_STATUS, PRIORITY } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { cn, timeAgo } from '@/lib/utils';

const STATUS_COLORS = {
  active: '#0d9488',
  pending_review: '#d97706',
  closed: '#94a3b8',
  archived: '#cbd5e1',
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
      render: (inv) => (
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

      {/* Status chips */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setParam('status', 'all', 'all')}
          className={cn(
            'rounded-full border px-3 py-1.5 text-xs font-medium transition-colors',
            status === 'all' ? 'border-navy-700 bg-navy-800 text-white' : 'border-slate-200 bg-white text-navy-500 hover:border-navy-300'
          )}
        >
          All <span className="opacity-60">{result ? Object.values(counts).reduce((a, b) => a + b, 0) : '…'}</span>
        </button>
        {Object.entries(INVESTIGATION_STATUS).map(([key, meta]) => (
          <button
            key={key}
            type="button"
            onClick={() => setParam('status', key, 'all')}
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors',
              status === key ? 'border-navy-700 bg-navy-800 text-white' : 'border-slate-200 bg-white text-navy-500 hover:border-navy-300'
            )}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
            {meta.label} <span className="opacity-60">{counts[key] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
        <div className="space-y-4 xl:col-span-3">
          {/* Filter bar */}
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="w-full sm:w-64">
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
            <div className="w-40">
              <Select value={status} onChange={(e) => setParam('status', e.target.value, 'all')} options={statusOptions} aria-label="Filter by status" />
            </div>
            <div className="w-40">
              <Select value={priority} onChange={(e) => setParam('priority', e.target.value, 'all')} options={priorityOptions} aria-label="Filter by priority" />
            </div>
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                icon={X}
                onClick={() => {
                  setInputValue('');
                  setSearchParams({}, { replace: true });
                }}
              >
                Clear filters
              </Button>
            )}
          </div>

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

        {/* Side panel */}
        <div className="space-y-6">
          <ChartCard title="By status" bodyClassName="pt-2">
            <StatusDonut
              size={150}
              data={[
                { label: 'Active', value: counts.active || 0, color: STATUS_COLORS.active },
                { label: 'Pending review', value: counts.pending_review || 0, color: STATUS_COLORS.pending_review },
                { label: 'Closed', value: counts.closed || 0, color: STATUS_COLORS.closed },
                { label: 'Archived', value: counts.archived || 0, color: STATUS_COLORS.archived },
              ]}
            />
          </ChartCard>

          <ChartCard title="By priority" bodyClassName="pt-2 space-y-3">
            {Object.entries(PRIORITY).map(([key, meta]) => {
              const value = items.filter((i) => i.priority === key).length;
              const pct = items.length ? Math.round((value / items.length) * 100) : 0;
              return (
                <div key={key}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium text-navy-500">{meta.label}</span>
                    <span className="text-navy-400">{value}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: meta.color }} />
                  </div>
                </div>
              );
            })}
          </ChartCard>
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
