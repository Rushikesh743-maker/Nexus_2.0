import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';


const VARIANTS = {
  primary: 'bg-teal-600 text-white shadow-sm hover:bg-teal-700 focus-visible:ring-teal-600 disabled:bg-teal-600/50',
  secondary: 'bg-navy-800 text-white shadow-sm hover:bg-navy-700 focus-visible:ring-navy-700 disabled:bg-navy-800/50',
  outline:
    'border border-slate-300 bg-white text-navy-700 shadow-sm hover:bg-slate-50 hover:text-navy-900 focus-visible:ring-navy-300',
  ghost: 'text-navy-500 hover:bg-slate-100 hover:text-navy-800 focus-visible:ring-navy-300',
  subtle: 'bg-teal-50 text-teal-700 hover:bg-teal-100 focus-visible:ring-teal-500',
  danger: 'bg-rose-600 text-white shadow-sm hover:bg-rose-700 focus-visible:ring-rose-600 disabled:bg-rose-600/50',
};

const SIZES = {
  sm: 'h-8 gap-1.5 px-3 text-xs',
  md: 'h-9 gap-2 px-3.5 text-sm',
  lg: 'h-10 gap-2 px-4 text-sm',
  icon: 'h-9 w-9 justify-center',
  iconSm: 'h-7 w-7 justify-center',
};

export function buttonClasses(variant = 'primary', size = 'md', className) {
  return cn(
    'inline-flex select-none items-center justify-center whitespace-nowrap rounded-lg font-medium transition-colors',
    'focus-visible:ring-2 focus-visible:ring-offset-1',
    'disabled:pointer-events-none disabled:opacity-80',
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
  children,
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={buttonClasses(variant, size, className)}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden />
      )}
      {children}
    </button>
  );
}

export function IconButton({ icon: Icon, label, variant = 'ghost', size = 'icon', className, ...props }) {
  return (
    <button type="button" aria-label={label} title={label} className={buttonClasses(variant, size, className)} {...props}>
      <Icon className={size === 'iconSm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} aria-hidden />
    </button>
  );
}
