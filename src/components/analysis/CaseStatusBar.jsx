import { ChevronDown } from 'lucide-react';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { CNA_ROLES } from '@/services/cnaService';
import { cn } from '@/lib/utils';

/**
 * Live status strip for the analysis case, mirroring the reference console's
 * header: the two figures an investigator checks constantly, and the role the
 * request is being made as.
 *
 * The role selector is not cosmetic — the backend checks the permission and
 * writes an audit entry before it answers, so changing it here genuinely
 * changes what comes back.
 */
export function CaseStatusBar({ className, onRoleChange }) {
  const { data, reload } = useCnaResource(() => cnaService.getStats(), []);

  function pick(token) {
    cnaService.setRoleToken(token);
    reload();
    onRoleChange?.(token);
  }

  const current = cnaService.getRoleToken();

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

      {/* Role */}
      <span className="relative inline-flex">
        <select
          value={current}
          onChange={(e) => pick(e.target.value)}
          aria-label="Acting as"
          className="appearance-none rounded border border-line bg-surface py-1 pl-2.5 pr-7 font-mono text-[11px] text-navy-700 outline-none transition-colors hover:border-line-strong focus:border-accent"
        >
          {CNA_ROLES.map((r) => (
            <option key={r.token} value={r.token}>
              {r.label}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-navy-400"
          aria-hidden
        />
      </span>
    </div>
  );
}
