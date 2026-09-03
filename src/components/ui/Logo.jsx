import { cn } from '@/lib/utils';
import { APP_NAME, APP_TAGLINE } from '@/lib/constants';

/**
 * Wordmark.
 *
 * The mark is a magnifying glass held over a three-node link — investigation
 * meets network analysis, the two things this product does. It is monochrome
 * and inherits `currentColor`, so it sits correctly on paper, on ink, and in
 * both themes without a variant per surface.
 */
export function Logo({ compact = false, className, withTagline = false }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5 text-navy-900', className)}>
      <svg viewBox="0 0 28 28" className="h-6 w-6 shrink-0" aria-hidden fill="none">
        {/* Network under glass: links first, so the nodes sit on top of them. */}
        <path
          d="M8.4 9.6 15.2 9.6 M8.4 9.6 11.8 15.6 M15.2 9.6 11.8 15.6"
          stroke="currentColor"
          strokeWidth="1.1"
          strokeLinecap="round"
          opacity="0.42"
        />
        <circle cx="8.4" cy="9.6" r="1.7" fill="currentColor" />
        <circle cx="15.2" cy="9.6" r="1.7" fill="currentColor" opacity="0.55" />
        <circle cx="11.8" cy="15.6" r="1.7" fill="currentColor" opacity="0.55" />

        {/* Lens and handle, drawn over the network to frame it as evidence. */}
        <circle cx="11.8" cy="11.8" r="8.3" stroke="currentColor" strokeWidth="1.6" />
        <path d="M17.7 17.7 24 24" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" />
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
