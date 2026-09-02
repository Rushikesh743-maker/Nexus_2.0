import { cn, hashString, initials } from '@/lib/utils';

const TONES = ['#0d9488', '#0284c7', '#7c3aed', '#d97706', '#e11d48', '#334e68'];

const SIZES = {
  xs: 'h-6 w-6 text-[9px]',
  sm: 'h-7 w-7 text-[10px]',
  md: 'h-9 w-9 text-[11px]',
  lg: 'h-12 w-12 text-sm',
};

export function Avatar({ name = '', size = 'md', className, ring = false, title }) {
  const tone = TONES[hashString(name) % TONES.length];
  return (
    <span
      title={title || name}
      style={{ backgroundColor: tone }}
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-white',
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
