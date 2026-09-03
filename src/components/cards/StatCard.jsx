import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';

/**
 * Headline figure.
 *
 * Matches the reference console: a coloured rule along the top edge, an
 * uppercase mono label, the figure set large in the mono face, and a caption
 * that says what produced it. No icon — in a grid of four, the icons were
 * decoration competing with the numbers, which are the actual signal.
 *
 * `tone` accepts a status role ("critical", "warning", "good") for the rule
 * and the figure, so a high-severity count reads as one at a glance.
 */
const TONE_COLOR = {
  accent: 'var(--accent)',
  critical: 'var(--critical)',
  warning: 'var(--warning)',
  serious: 'var(--serious)',
  good: 'var(--good)',
  neutral: 'var(--ink-400)',
};

export function StatCard({ label, value, sub, tone = 'accent', to, className }) {
  const color = TONE_COLOR[tone] || TONE_COLOR.accent;
  const emphasised = tone !== 'accent' && tone !== 'neutral';

  const body = (
    <Card className={cn('relative overflow-hidden p-4 pt-[15px]', to && 'hover-lift', className)}>
      {/* The rule is the card's only chrome, and it carries the status role. */}
      <span
        className="absolute inset-x-0 top-0 h-[2px]"
        style={{ background: color }}
        aria-hidden
      />
      <p className="label-micro leading-[1.4]">{label}</p>
      <p
        className="figure mt-2 text-[30px] font-semibold leading-none tracking-[-0.01em]"
        style={{ color: emphasised ? color : 'var(--ink-900)' }}
      >
        {value ?? '—'}
      </p>
      {sub && <p className="mt-2 text-[11.5px] leading-snug text-navy-400">{sub}</p>}
    </Card>
  );

  if (to) {
    return (
      <Link to={to} className="block rounded-lg">
        {body}
      </Link>
    );
  }
  return body;
}
