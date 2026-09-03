/**
 * The standing disclosure strip, carried over from the reference console.
 *
 * It sits above everything, on every screen, and is deliberately not
 * dismissible: a demonstration system showing fabricated people, numbers and
 * cases should say so at all times, not once at sign-in. The dashed rule is
 * what keeps it reading as a system notice rather than as page content.
 */
export function SyntheticBanner() {
  return (
    <div
      role="note"
      className="relative z-40 border-b border-dashed px-4 py-1.5 text-center"
      style={{ background: 'var(--surface-sunken)', borderColor: 'var(--line-strong)' }}
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-navy-500">
        Demonstration system — every person, number, case and transaction shown is synthetic and
        fictional.
      </p>
    </div>
  );
}
