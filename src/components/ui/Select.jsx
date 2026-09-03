import { useId } from 'react';
import { ChevronDown } from 'lucide-react';
import { Field, inputBase, inputError } from './Input';
import { cn } from '@/lib/utils';

export function Select({ label, error, hint, required, options = [], children, className, ...props }) {
  const autoId = useId();
  const id = props.id || autoId;
  return (
    <Field label={label} htmlFor={id} error={error} hint={hint} required={required}>
      <div className="relative">
        <select
          id={id}
          required={required}
          aria-invalid={Boolean(error)}
          className={cn(inputBase, 'appearance-none pr-8', error && inputError, className)}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-300" aria-hidden />
      </div>
    </Field>
  );
}
