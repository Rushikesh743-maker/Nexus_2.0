import { cn } from '@/lib/utils';

function toneFor(value) {
  if (value >= 80) return { bar: 'bg-emerald-500', text: 'text-emerald-600' };
  if (value >= 60) return { bar: 'bg-sky-500', text: 'text-sky-600' };
  return { bar: 'bg-amber-500', text: 'text-amber-600' };
}

/** Horizontal 0–100 confidence indicator. */
export function ConfidenceMeter({ value = 0, label = 'Confidence', className }) {
  const tone = toneFor(value);
  return (
    <div className={cn('w-full', className)}>
      <div className="mb-1 flex items-center justify-between text-[11px] font-medium">
        <span className="text-navy-400">{label}</span>
        <span className={tone.text}>{value}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className={cn('h-full rounded-full transition-[width]', tone.bar)} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  );
}
