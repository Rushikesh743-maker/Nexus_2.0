import { useId } from 'react';
import { cn } from '@/lib/utils';

export const inputBase =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-navy-800 shadow-sm transition-colors placeholder:text-navy-300 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/30 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-navy-300';
export const inputError = 'border-rose-400 focus:border-rose-500 focus:ring-rose-500/25';

export function Field({ label, htmlFor, error, hint, required, className, children }) {
  return (
    <div className={cn('w-full', className)}>
      {label && (
        <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium text-navy-700">
          {label}
          {required && <span className="ml-0.5 text-rose-500">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 text-xs font-medium text-rose-600">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-navy-300">{hint}</p>
      ) : null}
    </div>
  );
}

export function Input({ label, error, hint, icon: Icon, required, className, ...props }) {
  const autoId = useId();
  const id = props.id || autoId;
  return (
    <Field label={label} htmlFor={id} error={error} hint={hint} required={required}>
      <div className="relative">
        {Icon && (
          <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-navy-300" aria-hidden />
        )}
        <input
          id={id}
          required={required}
          aria-invalid={Boolean(error)}
          className={cn(inputBase, Icon && 'pl-9', error && inputError, className)}
          {...props}
        />
      </div>
    </Field>
  );
}
