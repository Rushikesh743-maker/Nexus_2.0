import { useEffect, useState } from 'react';
import { Modal } from '@/components/modals/Modal';
import { Badge } from '@/components/ui/Badge';
import { Button, buttonClasses } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/LoadingState';
import { investigationService } from '@/services';
import { PRIORITY } from '@/lib/constants';
import { Link } from 'react-router-dom';
import { timeAgo } from '@/lib/utils';

/**
 * Pick an active investigation before jumping to a case-scoped tool
 * (upload evidence, view network, view timeline).
 */
export function CasePickerModal({ open, onClose, title, description, ctaLabel = 'Continue', onSelect }) {
  const [cases, setCases] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    setError(null);
    investigationService
      .list({ status: 'active' })
      .then((r) => active && setCases(r.items))
      .catch((e) => {
        if (!active) return;
        setError(e);
        setCases([]);
      });
    return () => {
      active = false;
    };
  }, [open, reloadKey]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
      }
    >
      {cases === null ? (
        <div className="space-y-2.5">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <p className="py-4 text-center text-[13px] text-navy-400">Could not load investigations. {error.message}</p>
      ) : cases.length === 0 ? (
        <EmptyState
          title="No active investigations"
          description="Create an investigation and upload evidence to begin analysis."
          action={
            <Link to="/investigations/new" className={buttonClasses('primary', 'sm')}>
              Create Investigation
            </Link>
          }
        />
      ) : (
        <ul className="space-y-2">
          {cases.map((inv) => {
            const priority = PRIORITY[inv.priority] || PRIORITY.low;
            return (
              <li key={inv.id}>
                <button
                  type="button"
                  onClick={() => {
                    onSelect?.(inv);
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 rounded-lg border border-slate-200 p-3 text-left transition-colors hover:border-teal-400 hover:bg-teal-50/40"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="shrink-0 rounded bg-navy-50 px-1.5 py-0.5 font-mono text-[11px] font-medium text-navy-500">
                        {inv.code}
                      </span>
                      <span className="truncate text-[13px] font-semibold text-navy-800">{inv.title}</span>
                    </span>
                    <span className="mt-1 block text-[11px] text-navy-400">
                      {inv.stats.evidence} evidence · {inv.stats.entities} entities · updated {timeAgo(inv.updatedAt)}
                    </span>
                  </span>
                  <Badge variant={priority.variant}>{priority.label}</Badge>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}
