import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ClipboardList, Plus, Download, FileText, Eye } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/modals/Modal';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DataTable } from '@/components/tables/DataTable';
import { Badge } from '@/components/ui/Badge';
import { ReportPreviewModal } from '@/components/reports/ReportPreviewModal';
import { Avatar } from '@/components/ui/Avatar';
import { Tooltip } from '@/components/ui/Tooltip';
import { useInvestigation } from './InvestigationLayout';
import { intelligenceService } from '@/services';
import { REPORT_STATUS, REPORT_TYPES } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { formatDate } from '@/lib/utils';

export function ReportsPage() {
  const { investigation } = useInvestigation();
  useDocumentTitle(`${investigation.code} · Reports`);
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [preview, setPreview] = useState(null);
  const [open, setOpen] = useState(() => searchParams.get('request') === '1');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ type: 'case_summary', format: 'PDF', note: '' });

  const closeRequest = () => {
    setOpen(false);
    if (searchParams.get('request')) setSearchParams({}, { replace: true });
  };

  useEffect(() => {
    let active = true;
    setBusy(true);
    intelligenceService
      .getReports(investigation.id)
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
    return () => {
      active = false;
    };
  }, [investigation.id, reloadKey]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await intelligenceService.createReport(investigation.id, form);
      toast.info('Report queued', 'Document generation runs server-side — this demo records the request only.');
      setOpen(false);
      setReloadKey((k) => k + 1);
    } catch (err) {
      toast.error('Could not queue report', err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = () => {
    toast.info('Files are produced by the document service', 'Not available in the frontend-only build.');
  };

  const columns = [
    {
      key: 'title',
      header: 'Report',
      render: (rep) => (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-400">
            <FileText className="h-4 w-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-navy-800">{rep.title}</p>
            <p className="text-[11px] uppercase tracking-wide text-navy-300">
              {rep.id} · {(REPORT_TYPES[rep.type] || REPORT_TYPES.case_summary).label}
            </p>
          </div>
        </div>
      ),
    },
    { key: 'format', header: 'Format', render: (rep) => <Badge variant="neutral">{rep.format}</Badge> },
    {
      key: 'requestedBy',
      header: 'Requested by',
      render: (rep) => (
        <span className="flex items-center gap-2 text-[13px]">
          <Avatar name={rep.requestedBy} size="xs" />
          {rep.requestedBy}
        </span>
      ),
    },
    {
      key: 'createdAt',
      header: 'Requested',
      className: 'text-right',
      render: (rep) => <span className="text-[12px] text-navy-400">{formatDate(rep.createdAt)}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (rep) => {
        const meta = REPORT_STATUS[rep.status] || REPORT_STATUS.queued;
        return (
          <Badge variant={meta.variant} dot>
            {meta.label}
          </Badge>
        );
      },
    },
    {
      key: 'actions',
      header: '',
      headerClassName: 'w-16',
      render: (rep) => (
        <Tooltip label={rep.status === 'ready' ? 'Document service not connected (mock)' : 'Not ready'} side="left">
          <Button
            variant="ghost"
            size="iconSm"
            icon={Download}
            aria-label={`Download ${rep.title}`}
            disabled={rep.status !== 'ready'}
            onClick={handleDownload}
          />
        </Tooltip>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-navy-400">
          Report generation runs server-side. This view tracks requests and their status.
        </p>
        <Button icon={Plus} onClick={() => setOpen(true)}>
          Request report
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={result?.items || []}
        isLoading={busy}
        error={error}
        onRetry={() => setReloadKey((k) => k + 1)}
        emptyIcon={ClipboardList}
        emptyTitle="No reports requested yet"
        emptyDescription="Request a case summary, evidence index, network analysis or timeline digest."
        pageSize={8}
      />

      <ReportPreviewModal
        open={Boolean(preview)}
        onClose={() => setPreview(null)}
        investigation={investigation}
      />

      <Modal
        open={open}
        onClose={closeRequest}
        title="Request report"
        description={`For ${investigation.code} · ${investigation.title}`}
        footer={
          <>
            <Button variant="outline" onClick={closeRequest} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="new-report-form" loading={saving}>
              Queue report
            </Button>
          </>
        }
      >
        <form id="new-report-form" onSubmit={handleCreate} className="space-y-4">
          <Select
            label="Type"
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
            options={Object.entries(REPORT_TYPES).map(([value, meta]) => ({ value, label: meta.label }))}
          />
          <Select
            label="Format"
            value={form.format}
            onChange={(e) => setForm({ ...form, format: e.target.value })}
            options={[
              { value: 'PDF', label: 'PDF' },
              { value: 'DOCX', label: 'DOCX' },
            ]}
          />
          <Input
            label="Note (optional)"
            placeholder="Anything the report should emphasise…"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </form>
      </Modal>
    </div>
  );
}
