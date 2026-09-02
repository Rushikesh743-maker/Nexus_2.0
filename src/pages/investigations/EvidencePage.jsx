import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Search, FolderOpen, Eye, Download, Info, Trash2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button, IconButton } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { Tooltip } from '@/components/ui/Tooltip';
import { DataTable } from '@/components/tables/DataTable';
import { ConfirmDialog } from '@/components/modals/ConfirmDialog';
import { UploadEvidenceModal } from '@/components/evidence/UploadEvidenceModal';
import { EvidenceDetailsDrawer } from '@/components/evidence/EvidenceDetailsDrawer';
import { useInvestigation } from './InvestigationLayout';
import { evidenceService } from '@/services';
import { EVIDENCE_TYPES, EVIDENCE_STATUS, FILE_TYPES } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { useAuth } from '@/context/AuthContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { cn, formatFileSize, formatDate } from '@/lib/utils';

const FILE_TYPE_OPTIONS = [
  { value: 'all', label: 'All file types' },
  ...Object.entries(FILE_TYPES).map(([value, meta]) => ({ value, label: meta.label })),
];

const LANGUAGE_OPTIONS = [
  { value: 'all', label: 'All languages' },
  { value: 'English', label: 'English' },
  { value: 'Marathi', label: 'Marathi' },
  { value: 'Hindi', label: 'Hindi' },
  { value: 'unknown', label: 'Not applicable' },
];

const STATUS_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  ...Object.entries(EVIDENCE_STATUS).map(([value, meta]) => ({ value, label: meta.label })),
];

const DATE_OPTIONS = [
  { value: 'all', label: 'All time' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
];

export function EvidencePage() {
  const { investigation, refresh } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Evidence`);
  const toast = useToast();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const [stats, setStats] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [filters, setFilters] = useState({
    search: '',
    fileType: 'all',
    language: 'all',
    status: 'all',
    uploadedWithin: 'all',
  });

  const [selected, setSelected] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(() => searchParams.get('log') === '1');

  /* Deep link: /evidence?evidence=<id> opens the record's details drawer. */
  useEffect(() => {
    const eid = searchParams.get('evidence');
    if (!eid) return undefined;
    let active = true;
    evidenceService
      .get(eid)
      .then((record) => active && setSelected(record))
      .catch(() => {});
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Stats (header chips) */
  useEffect(() => {
    let active = true;
    evidenceService
      .getStats(investigation.id)
      .then((s) => active && setStats(s))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [investigation.id, reloadKey]);

  /* Filtered list (debounced) */
  useEffect(() => {
    let active = true;
    setBusy(true);
    const timer = setTimeout(() => {
      evidenceService
        .list(investigation.id, filters)
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
    }, 160);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [investigation.id, filters, reloadKey]);

  const columns = useMemo(
    () => [
      {
        key: 'file',
        header: 'File',
        render: (ev) => {
          const typeMeta = EVIDENCE_TYPES[ev.type] || EVIDENCE_TYPES.document;
          return (
            <div className="flex items-center gap-3">
              <span
                style={{ backgroundColor: `${typeMeta.color}14`, color: typeMeta.color }}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
              >
                <typeMeta.icon className="h-4 w-4" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="max-w-[280px] truncate text-[13px] font-semibold text-navy-800">{ev.title}</p>
                <p className="font-mono text-[11px] text-navy-300">{ev.refNo}</p>
              </div>
            </div>
          );
        },
      },
      {
        key: 'type',
        header: 'Type',
        render: (ev) => <Badge variant="neutral">{FILE_TYPES[ev.fileType]?.label || 'File'}</Badge>,
      },
      {
        key: 'size',
        header: 'Size',
        render: (ev) => <span className="text-[13px] text-navy-500">{formatFileSize(ev.size)}</span>,
      },
      {
        key: 'uploaded',
        header: 'Uploaded',
        render: (ev) => <span className="text-[12px] text-navy-400">{formatDate(ev.collectedAt)}</span>,
      },
      {
        key: 'language',
        header: 'Language',
        render: (ev) => <span className="text-[13px] text-navy-500">{ev.language || '—'}</span>,
      },
      {
        key: 'status',
        header: 'Status',
        render: (ev) => {
          const meta = EVIDENCE_STATUS[ev.status] || EVIDENCE_STATUS.uploaded;
          return (
            <Badge variant={meta.variant} dot>
              {meta.label}
            </Badge>
          );
        },
      },
      {
        key: 'actions',
        header: 'Actions',
        headerClassName: 'w-44',
        render: (ev) => (
          <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
            <Tooltip label="View" side="left" className="w-auto">
              <IconButton
                icon={Eye}
                label={`View ${ev.title}`}
                size="iconSm"
                onClick={() => toast.info('Preview needs the document service', 'In-app file preview arrives with the backend integration.')}
              />
            </Tooltip>
            <Tooltip label="Download" side="left" className="w-auto">
              <IconButton
                icon={Download}
                label={`Download ${ev.title}`}
                size="iconSm"
                onClick={() => toast.info('File retrieval needs the document service', 'Downloads will work once the backend API is connected.')}
              />
            </Tooltip>
            <Tooltip label="Details" side="left" className="w-auto">
              <IconButton icon={Info} label={`Details of ${ev.title}`} size="iconSm" onClick={() => setSelected(ev)} />
            </Tooltip>
            <Tooltip label="Delete" side="left" className="w-auto">
              <IconButton
                icon={Trash2}
                label={`Delete ${ev.title}`}
                size="iconSm"
                className="hover:bg-rose-50 hover:text-rose-600"
                onClick={() => setConfirmDelete(ev)}
              />
            </Tooltip>
          </div>
        ),
      },
    ],
    [toast]
  );

  const chips = [
    { id: 'all', label: 'Total Files', value: stats?.total },
    { id: 'processed', label: 'Processed', value: stats?.processed },
    { id: 'processing', label: 'Processing', value: stats?.processing },
    { id: 'needs_review', label: 'Needs Review', value: stats?.needsReview },
    { id: 'failed', label: 'Failed', value: stats?.failed },
  ];

  const setFilter = (key, value) => setFilters((f) => ({ ...f, [key]: value }));

  const handleChip = (id) => {
    setFilter('status', filters.status === id || id === 'all' ? 'all' : id);
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await evidenceService.remove(confirmDelete.id);
      toast.success('Evidence deleted', `${confirmDelete.refNo} removed from ${investigation.code}`);
      setSelected(null);
      setReloadKey((k) => k + 1);
      refresh();
    } catch (e) {
      toast.error('Could not delete evidence', e.message);
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  };

  const hasFilters =
    filters.search || filters.fileType !== 'all' || filters.language !== 'all' || filters.status !== 'all' || filters.uploadedWithin !== 'all';

  return (
    <div className="space-y-4">
      {/* Status summary chips */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5" role="group" aria-label="Evidence status summary">
        {chips.map((chip) => {
          const active = filters.status === chip.id || (chip.id === 'all' && filters.status === 'all');
          return (
            <button
              key={chip.id}
              type="button"
              onClick={() => handleChip(chip.id)}
              aria-pressed={active}
              className={cn(
                'rounded-xl border bg-white p-3.5 text-left shadow-card transition-colors',
                active ? 'border-teal-500 ring-1 ring-teal-500' : 'border-slate-200 hover:border-teal-300'
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-300">{chip.label}</p>
              <p className={cn('mt-1 text-2xl font-semibold leading-none', chip.id === 'failed' && (chip.value || 0) > 0 ? 'text-rose-600' : 'text-navy-900')}>
                {chip.value ?? '…'}
              </p>
            </button>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="w-full sm:w-52">
          <Input
            icon={Search}
            placeholder="Search evidence…"
            aria-label="Search evidence"
            value={filters.search}
            onChange={(e) => setFilter('search', e.target.value)}
          />
        </div>
        <div className="w-32">
          <Select value={filters.fileType} onChange={(e) => setFilter('fileType', e.target.value)} options={FILE_TYPE_OPTIONS} aria-label="Filter by file type" />
        </div>
        <div className="w-36">
          <Select value={filters.language} onChange={(e) => setFilter('language', e.target.value)} options={LANGUAGE_OPTIONS} aria-label="Filter by language" />
        </div>
        <div className="w-36">
          <Select value={filters.status} onChange={(e) => setFilter('status', e.target.value)} options={STATUS_OPTIONS} aria-label="Filter by status" />
        </div>
        <div className="w-36">
          <Select value={filters.uploadedWithin} onChange={(e) => setFilter('uploadedWithin', e.target.value)} options={DATE_OPTIONS} aria-label="Filter by upload date" />
        </div>
        {hasFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              setFilters({ search: '', fileType: 'all', language: 'all', status: 'all', uploadedWithin: 'all' })
            }
          >
            Clear
          </Button>
        )}
        <Button icon={Plus} className="ml-auto" onClick={() => setUploadOpen(true)}>
          Upload Evidence
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={result?.items || []}
        isLoading={busy}
        error={error}
        onRetry={() => setReloadKey((k) => k + 1)}
        onRowClick={setSelected}
        emptyIcon={FolderOpen}
        emptyTitle={hasFilters ? 'No evidence matches these filters' : 'No evidence yet'}
        emptyDescription={
          hasFilters
            ? 'Adjust the search term or clear the filters to see all files.'
            : 'Upload FIR documents, CDR exports, statements or media files to begin building the case record.'
        }
        emptyAction={
          !hasFilters && (
            <Button size="sm" icon={Plus} onClick={() => setUploadOpen(true)}>
              Upload Evidence
            </Button>
          )
        }
        pageSize={8}
      />

      {/* Upload flow */}
      <UploadEvidenceModal
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          if (searchParams.get('log')) setSearchParams({}, { replace: true });
        }}
        investigation={investigation}
        uploadedBy={user?.name || 'Unassigned'}
        onUploaded={() => setReloadKey((k) => k + 1)}
      />

      {/* Details drawer */}
      <EvidenceDetailsDrawer
        evidence={selected}
        onClose={() => {
          setSelected(null);
          if (searchParams.get('evidence')) setSearchParams({}, { replace: true });
        }}
        onDelete={setConfirmDelete}
      />

      {/* Delete confirmation */}
      <ConfirmDialog
        open={Boolean(confirmDelete)}
        onClose={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
        loading={deleting}
        title="Delete evidence"
        confirmLabel="Delete"
        message={`Permanently remove ${confirmDelete?.refNo} — “${confirmDelete?.title}” — from ${investigation.code}? The chain of custody record is deleted with it.`}
      />
    </div>
  );
}
