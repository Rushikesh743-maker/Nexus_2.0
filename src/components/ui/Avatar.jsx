import { cn, hashString, initials } from '@/lib/utils';

/**
 * Identity disc.
 *
 * Colour here does carry information — it is what lets an analyst tell two
 * investigators apart at a glance in a dense table — so it is kept. What is
 * dropped is the saturation: a soft tint with ink initials reads as identity
 * rather than as decoration, and it stops avatars being the loudest thing on
 * a page whose whole point is the data.
 */
const TONES = [
  'var(--data-teal)',
  'var(--data-sky)',
  'var(--data-violet)',
  'var(--data-amber)',
  'var(--data-rose)',
  'var(--data-emerald)',
];

const SIZES = {
  xs: 'h-5 w-5 text-[8px]',
  sm: 'h-7 w-7 text-[9px]',
  md: 'h-8 w-8 text-[10px]',
  lg: 'h-11 w-11 text-[13px]',
};

export function Avatar({ name = '', size = 'md', className, ring = false, title }) {
  const tone = TONES[hashString(name) % TONES.length];
  return (
    <span
      title={title || name}
      style={{
        backgroundColor: `color-mix(in srgb, ${tone} 18%, transparent)`,
        color: tone,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${tone} 30%, transparent)`,
      }}
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold uppercase',
        SIZES[size] || SIZES.md,
        ring && 'ring-2 ring-white',
        className
      )}
      aria-hidden={!title && !name}
    >
      {initials(name) || '?'}
    </span>
  );
}
