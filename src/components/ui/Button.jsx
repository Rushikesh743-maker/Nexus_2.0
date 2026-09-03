import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Buttons.
 *
 * The primary action is a solid block of ink — under the design thesis the
 * loudest affordance available is contrast, not a hue, and colour is kept for
 * data. In dark mode the same token inverts to paper-on-ink, so "primary" stays
 * the strongest thing on screen in both themes without a second definition.
 */
const VARIANTS = {
  primary: 'bg-action text-action-on hover:bg-action-hover disabled:opacity-45',
  secondary: 'bg-action text-action-on hover:bg-action-hover disabled:opacity-45',
  outline: 'border border-line bg-surface text-navy-700 hover:border-line-strong hover:text-navy-900',
  ghost: 'text-navy-500 hover:bg-slate-50 hover:text-navy-900',
  subtle: 'bg-slate-50 text-navy-700 hover:bg-slate-100 hover:text-navy-900',
  accent: 'bg-accent text-accent-on hover:bg-accent-strong disabled:opacity-45',
  danger: 'text-white hover:opacity-90 disabled:opacity-45',
};

/* The one variant that must carry a hue: destructive intent. */
const VARIANT_STYLE = {
  danger: { backgroundColor: 'var(--data-rose)', color: 'var(--surface)' },
};

const SIZES = {
  sm: 'h-7 gap-1.5 px-2.5 text-[12px]',
  md: 'h-8 gap-2 px-3 text-[13px]',
  lg: 'h-9 gap-2 px-4 text-[13px]',
  icon: 'h-8 w-8 justify-center',
  iconSm: 'h-7 w-7 justify-center',
};

export function buttonClasses(variant = 'primary', size = 'md', className) {
  return cn(
    'inline-flex select-none items-center justify-center whitespace-nowrap rounded-md font-medium',
    'transition-colors duration-150 ease-instrument',
    'disabled:pointer-events-none',
    VARIANTS[variant] || VARIANTS.primary,
    SIZES[size] || SIZES.md,
    className
  );
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon: Icon,
  loading = false,
  disabled,
  type = 'button',
  className,
  style,
  children,
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={buttonClasses(variant, size, className)}
      style={{ ...VARIANT_STYLE[variant], ...style }}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      ) : (
        Icon && <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
      )}
      {children}
    </button>
  );
}

export function IconButton({ icon: Icon, label, variant = 'ghost', size = 'icon', className, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={buttonClasses(variant, size, className)}
      {...props}
    >
      <Icon className={size === 'iconSm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} aria-hidden />
    </button>
  );
}
