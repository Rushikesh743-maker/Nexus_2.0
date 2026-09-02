import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { IconButton } from '@/components/ui/Button';

/**
 * Right-side slide-in drawer with overlay. Closes on Escape / overlay click.
 */
export function Drawer({ open, onClose, title, subtitle, footer, children, width = 460 }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[80]" role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Details panel'}>
      <div className="animate-fade-in absolute inset-0 bg-navy-950/40" onClick={onClose} aria-hidden />
      <aside
        style={{ maxWidth: width }}
        className="animate-slide-in-right absolute inset-y-0 right-0 flex w-full flex-col border-l border-slate-200 bg-white shadow-xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="truncate text-base font-semibold text-navy-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 truncate font-mono text-[11px] text-navy-300">{subtitle}</p>}
          </div>
          <IconButton icon={X} label="Close panel" onClick={onClose} className="-mr-1 -mt-1" />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">{children}</div>
        {footer && <div className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3">{footer}</div>}
      </aside>
    </div>,
    document.body
  );
}
