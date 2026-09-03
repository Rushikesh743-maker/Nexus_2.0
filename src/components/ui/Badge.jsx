import { cn } from '@/lib/utils';

/**
 * Badges.
 *
 * This is one of the few places colour is spent, because a badge here almost
 * always encodes meaning — severity, status, corroboration. The fills are the
 * semantic data tokens, so they stay legible against both grounds.
 *
 * `neutral` deliberately carries no hue: most badges in a dense table are
 * labels rather than signals, and tinting them all would flatten the ones
 * that matter.
 */
const VARIANTS = {
  success: { background: 'var(--data-emerald-soft)', color: 'var(--data-emerald)' },
  warning: { background: 'var(--data-amber-soft)', color: 'var(--data-amber)' },
  danger: { background: 'var(--data-rose-soft)', color: 'var(--data-rose)' },
  info: { background: 'var(--data-sky-soft)', color: 'var(--data-sky)' },
  teal: { background: 'var(--accent-surface)', color: 'var(--accent-strong)' },
  violet: { background: 'var(--data-violet-soft)', color: 'var(--data-violet)' },
  neutral: { background: 'var(--surface-sunken)', color: 'var(--ink-600)' },
};

const DOTS = {
  success: 'var(--data-emerald)',
  warning: 'var(--data-amber)',
  danger: 'var(--data-rose)',
  info: 'var(--data-sky)',
  teal: 'var(--accent)',
  violet: 'var(--data-violet)',
  neutral: 'var(--ink-400)',
};

export function Badge({ variant = 'neutral', dot = false, className, style, children }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium leading-[1.35]',
        className
      )}
      style={{ ...(VARIANTS[variant] || VARIANTS.neutral), ...style }}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ background: DOTS[variant] || DOTS.neutral }}
          aria-hidden
        />
      )}
      {children}
    </span>
  );
}
