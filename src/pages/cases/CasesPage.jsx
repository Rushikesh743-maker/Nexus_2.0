import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FolderKanban, Plus, ServerOff } from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/modals/Modal';
import { Input, Field } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { DataTable } from '@/components/tables/DataTable';
import { StatusBadge, PriorityBadge } from '@/components/cases/StatusBadge';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService, V1Error } from '@/services/v1';
import { useToast } from '@/context/ToastContext';
import { formatDateTime } from '@/lib/utils';

const STATUS_OPTIONS = ['ACTIVE', 'OPEN', 'ON_HOLD', 'CLOSED'];
const PRIORITY_OPTIONS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

function NewCaseModal({ onClose, onCreated }) {
  const toast = useToast();
  const [form, setForm] = useState({ title: '', status: 'OPEN', priority: 'MEDIUM', description: '' });
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const created = await caseService.createCase({
        title: form.title.trim(),
        status: form.status,
        priority: form.priority,
        description: form.description.trim() || null,
      });
      toast.success(`Case created — ${created.case_number}`);
      onCreated(created);
    } catch (err) {
      toast.error(err.message || 'Could not create case.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open title="New case" onClose={onClose} size="md">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Title" required>
          <Input
            autoFocus
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g. Unauthorised vehicle movement — Pune ring road"
          />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Status">
            <Select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              options={STATUS_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
          </Field>
          <Field label="Priority">
            <Select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
              options={PRIORITY_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
          </Field>
        </div>
        <Field label="Description">
          <Input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Initial working hypothesis or referral summary"
          />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving || !form.title.trim()} icon={Plus}>
            {saving ? 'Creating…' : 'Create case'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * Case registry — the live list of case files served by the platform API.
 * Distinct from the analysis "Investigations" screen, which is fed by the
 * demonstration pipeline.
 */
export function CasesPage() {
  const navigate = useNavigate();
  const { data: cases, error, loading, reload } = useCnaResource(() => caseService.listCases(), []);
  const [creating, setCreating] = useState(false);

  const columns = useMemo(
    () => [
      {
        key: 'case_number',
        header: 'Case',
        render: (c) => (
          <Link to={`/cases/${c.id}`} className="group block min-w-0">
            <span className="figure block text-[11.5px] text-navy-400">{c.case_number}</span>
            <span className="block truncate text-[13px] font-medium text-navy-800 group-hover:text-navy-950">
              {c.title}
            </span>
          </Link>
        ),
      },
      { key: 'status', header: 'Status', render: (c) => <StatusBadge status={c.status} /> },
      { key: 'priority', header: 'Priority', render: (c) => <PriorityBadge priority={c.priority} /> },
      {
        key: 'entities',
        header: 'Entities',
        className: 'text-right',
        render: (c) => <span className="figure text-[12.5px]">{c.counts.entities}</span>,
      },
      {
        key: 'relationships',
        header: 'Links',
        className: 'text-right',
        render: (c) => <span className="figure text-[12.5px]">{c.counts.relationships}</span>,
      },
      {
        key: 'updated_at',
        header: 'Updated',
        render: (c) => <span className="text-[12px] text-navy-400">{formatDateTime(c.updated_at)}</span>,
      },
    ],
    []
  );

  if (loading && !cases) return <PageLoader label="Loading cases…" />;

  if (error && !cases) {
    if (error instanceof V1Error && error.offline) {
      return (
        <div>
          <PageHeader
            title="Cases"
            description="Live case files served by the platform API."
            actions={<Button variant="outline" icon={ServerOff} onClick={reload}>Retry</Button>}
          />
          <ErrorState
            title="Case backend unreachable"
            description="The case registry is live-backed and has no offline fallback. Start the backend (python3 backend/run.py) and retry."
            onRetry={reload}
          />
        </div>
      );
    }
    return (
      <div>
        <PageHeader title="Cases" description="Live case files served by the platform API." />
        <ErrorState title="Could not load cases" description={error.message} onRetry={reload} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Cases"
        description="Every case file on the platform, live from PostgreSQL. Open a case for its entities, evidence, timeline and network."
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            New case
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={cases || []}
        getRowId={(c) => c.id}
        isLoading={loading}
        error={error}
        onRetry={reload}
        onRowClick={(c) => navigate(`/cases/${c.id}`)}
        emptyIcon={FolderKanban}
        emptyTitle="No cases yet"
        emptyDescription="Create the first case file to start building a network."
        emptyAction={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            New case
          </Button>
        }
      />

      {creating && (
        <NewCaseModal
          onClose={() => setCreating(false)}
          onCreated={(c) => {
            setCreating(false);
            navigate(`/cases/${c.id}`);
          }}
        />
      )}
    </div>
  );
}
