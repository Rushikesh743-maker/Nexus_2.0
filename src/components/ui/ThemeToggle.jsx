import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '@/context/ThemeContext';
import { cn } from '@/lib/utils';

const OPTIONS = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor },
];

/**
 * Three-state appearance control.
 *
 * "System" is a real option rather than an implied default, because an analyst
 * whose OS flips at dusk should not have to come back and change this — and
 * because a two-state switch cannot express "follow the machine".
 */
export function ThemeToggle({ className }) {
  const { preference, setTheme } = useTheme();

  return (
    <div
      className={cn('inline-flex items-center gap-0.5 rounded-md border border-line p-0.5', className)}
      role="radiogroup"
      aria-label="Appearance"
    >
      {OPTIONS.map((opt) => {
        const active = preference === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={`${opt.label} theme`}
            title={`${opt.label} theme`}
            onClick={() => setTheme(opt.id)}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded transition-colors duration-150',
              active
                ? 'bg-surface-inverse text-action-on'
                : 'text-navy-400 hover:bg-slate-50 hover:text-navy-800'
            )}
          >
            <opt.icon className="h-3.5 w-3.5" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}

/** Compact single-button variant for tight spaces. */
export function ThemeToggleButton({ className }) {
  const { isDark, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={isDark ? 'Light theme' : 'Dark theme'}
      className={cn(
        'flex h-8 w-8 items-center justify-center rounded-md border border-line text-navy-500 transition-colors hover:border-line-strong hover:text-navy-900',
        className
      )}
    >
      {isDark ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
    </button>
  );
}
