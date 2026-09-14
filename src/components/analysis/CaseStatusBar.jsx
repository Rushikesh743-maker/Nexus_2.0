import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { cn } from '@/lib/utils';

/**
 * Live status strip for the analysis case: the two figures an investigator
 * checks constantly, and the role the authenticated caller is acting as.
 *
 * The role is not selectable — it is the caller's role, resolved by the
 * backend from the verified Supabase identity (the request is authorized and
 * audited as that role).
 */
export function CaseStatusBar({ className }) {
  const { data } = useCnaResource(() => cnaService.getStats(), []);
  const { data: me } = useCnaResource(() => cnaService.me(), []);

  const roleLabel = me?.role === 'admin' ? 'Administrator' : 'Investigator';

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {/* Figures */}
      <span
        className="inline-flex items-center gap-1.5 rounded border border-line px-2.5 py-1"
        style={{ background: 'var(--surface-sunken)' }}
      >
        <span className="figure text-[12px] font-semibold text-navy-900">{data?.nodes ?? '—'}</span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-navy-500">entities</span>
        <span className="text-navy-300" aria-hidden>·</span>
        <span className="figure text-[12px] font-semibold text-navy-900">{data?.edges ?? '—'}</span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-navy-500">links</span>
      </span>

      <span
        className="inline-flex items-center gap-1.5 rounded border px-2.5 py-1"
        style={{
          background: 'var(--surface-sunken)',
          borderColor: data?.high_severity ? 'var(--critical)' : 'var(--line)',
        }}
      >
        <span
          className="figure text-[12px] font-semibold"
          style={{ color: data?.high_severity ? 'var(--critical)' : 'var(--ink-900)' }}
        >
          {data?.high_severity ?? '—'}
        </span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-navy-500">
          high-severity
        </span>
      </span>

      {/* Role (read-only: the authenticated caller's role) */}
      <span
        className="inline-flex items-center gap-1.5 rounded border border-line px-2.5 py-1"
        style={{ background: 'var(--surface-sunken)' }}
        title={me?.name || undefined}
      >
        <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-navy-500">acting as</span>
        <span className="font-mono text-[11px] text-navy-700">{me ? roleLabel : '—'}</span>
      </span>
    </div>
  );
}
