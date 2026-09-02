import { CheckCircle2, XCircle, Info, AlertTriangle, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const VARIANTS = {
  success: { icon: CheckCircle2, iconClass: 'text-emerald-500' },
  error: { icon: XCircle, iconClass: 'text-rose-500' },
  info: { icon: Info, iconClass: 'text-sky-500' },
  warning: { icon: AlertTriangle, iconClass: 'text-amber-500' },
};

function ToastItem({ toast, onDismiss }) {
  const { icon: Icon, iconClass } = VARIANTS[toast.variant] || VARIANTS.info;
  return (
    <div
      role="status"
      className="animate-fade-in pointer-events-auto flex w-full items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-dropdown"
    >
      <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', iconClass)} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-navy-800">{toast.message}</p>
        {toast.detail && <p className="mt-0.5 text-xs leading-relaxed text-navy-400">{toast.detail}</p>}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="rounded p-0.5 text-navy-300 transition-colors hover:text-navy-600"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

export function ToastViewport({ toasts, onDismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
