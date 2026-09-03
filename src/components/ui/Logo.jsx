import { cn } from '@/lib/utils';
import { APP_NAME, APP_TAGLINE } from '@/lib/constants';

/**
 * Wordmark.
 *
 * The mark is a three-node link — the smallest possible drawing of the thing
 * this product does. It is monochrome and inherits `currentColor`, so it sits
 * correctly on paper, on ink, and in both themes without a variant per surface.
 */
export function Logo({ compact = false, className, withTagline = false }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5 text-navy-900', className)}>
      <svg viewBox="0 0 28 28" className="h-6 w-6 shrink-0" aria-hidden fill="none">
        {/* Links first, so the nodes sit on top of them. */}
        <path
          d="M7 9.5 21 9.5 M7 9.5 14 19.5 M21 9.5 14 19.5"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeLinecap="round"
          opacity="0.42"
        />
        <circle cx="7" cy="9.5" r="2.4" fill="currentColor" />
        <circle cx="21" cy="9.5" r="2.4" fill="currentColor" opacity="0.55" />
        <circle cx="14" cy="19.5" r="2.4" fill="currentColor" opacity="0.55" />
      </svg>

      {!compact && (
        <span className="flex flex-col leading-none">
          <span className="text-[15px] font-semibold uppercase tracking-[0.2em]">{APP_NAME}</span>
          {withTagline && (
            <span className="label-micro mt-1.5 normal-case tracking-[0.16em]">{APP_TAGLINE}</span>
          )}
        </span>
      )}
    </span>
  );
}
