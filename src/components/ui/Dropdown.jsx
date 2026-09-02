import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Minimal dropdown menu. `trigger` is wrapped in a toggle; children render
 * inside a right-aligned popover that closes on outside click / Escape.
 */
export function Dropdown({ trigger, children, align = 'right', width = 208, className }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className={cn('relative inline-flex', className)} ref={ref}>
      <span className="inline-flex" onClick={() => setOpen((o) => !o)}>
        {trigger}
      </span>
      {open && (
        <div
          style={{ minWidth: width }}
          className={cn(
            'animate-fade-in absolute z-50 mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-dropdown',
            align === 'right' ? 'right-0' : 'left-0'
          )}
          role="menu"
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function DropdownItem({ icon: Icon, label, onClick, variant = 'default', disabled }) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        variant === 'danger'
          ? 'text-rose-600 hover:bg-rose-50'
          : 'text-navy-600 hover:bg-slate-50 hover:text-navy-900'
      )}
    >
      {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden />}
      {label}
    </button>
  );
}

export function DropdownDivider() {
  return <div className="my-1 border-t border-slate-100" role="separator" />;
}

export function DropdownLabel({ children }) {
  return <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-navy-300">{children}</div>;
}
