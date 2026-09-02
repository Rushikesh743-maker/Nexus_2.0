import { cn } from '@/lib/utils';
import { APP_NAME, APP_TAGLINE } from '@/lib/constants';

export function Logo({ variant = 'dark', compact = false, className, withTagline = false }) {
  const light = variant === 'light';
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <path d="M16 2 28 9v14L16 30 4 23V9z" fill={light ? '#134e4a' : '#102a43'} />
        <path d="M11 12h10M11 12l5 9M21 12l-5 9" stroke="#2dd4bf" strokeWidth="1.4" />
        <circle cx="11" cy="12" r="2.4" fill="#2dd4bf" />
        <circle cx="21" cy="12" r="2.4" fill="#2dd4bf" />
        <circle cx="16" cy="21" r="2.4" fill="#2dd4bf" />
      </svg>
      {!compact && (
        <span className="flex flex-col leading-none">
          <span
            className={cn(
              'text-[17px] font-bold tracking-[0.14em]',
              light ? 'text-white' : 'text-navy-900'
            )}
          >
            {APP_NAME}
          </span>
          {withTagline && (
            <span
              className={cn(
                'mt-1 text-[9px] font-medium uppercase tracking-[0.18em]',
                light ? 'text-teal-300/80' : 'text-navy-300'
              )}
            >
              {APP_TAGLINE}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
