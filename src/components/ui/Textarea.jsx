import { useId } from 'react';
import { Field, inputBase, inputError } from './Input';
import { cn } from '@/lib/utils';

export function Textarea({ label, error, hint, required, rows = 4, className, ...props }) {
  const autoId = useId();
  const id = props.id || autoId;
  return (
    <Field label={label} htmlFor={id} error={error} hint={hint} required={required}>
      <textarea
        id={id}
        rows={rows}
        required={required}
        aria-invalid={Boolean(error)}
        className={cn(inputBase, 'resize-y leading-relaxed', error && inputError, className)}
        {...props}
      />
    </Field>
  );
}
