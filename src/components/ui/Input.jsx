import { useId } from 'react';
import { cn } from '@/lib/utils';

export const inputBase =
  'w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-[13px] text-navy-800 transition-colors ' +
  'placeholder:text-navy-300 hover:border-line-strong focus:border-accent focus:outline-none ' +
  'disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-navy-300';
export const inputError = 'border-rose-400 focus:border-rose-500';

export function Field({ label, htmlFor, error, hint, required, className, children }) {
  return (
    <div className={cn('w-full', className)}>
      {label && (
        <label htmlFor={htmlFor} className="label-micro mb-1.5 block text-navy-500">
          {label}
          {required && <span className="ml-0.5 text-rose-500">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 text-[11px] font-medium text-rose-600">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-navy-400">{hint}</p>
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
          className={cn(inputBase, Icon && 'pl-8', error && inputError, className)}
          {...props}
        />
      </div>
    </Field>
  );
}
