import { AlertTriangle } from 'lucide-react';
import { Modal } from './Modal';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title = 'Are you sure?',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  loading = false,
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title={
        <span className="flex items-center gap-2">
          {tone === 'danger' && <AlertTriangle className="h-5 w-5 text-rose-500" aria-hidden />}
          {title}
        </span>
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={tone === 'danger' ? 'danger' : 'primary'} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className={cn('text-sm leading-relaxed text-navy-500')}>{message}</p>
    </Modal>
  );
}
