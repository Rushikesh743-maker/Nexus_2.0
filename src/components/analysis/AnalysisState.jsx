import { PlugZap, ShieldX, Info, PackageOpen } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/LoadingState';
import { CNA_DISCLOSURE, CNA_SYNTHETIC_NOTICE } from '@/lib/cna';
import { cn } from '@/lib/utils';

/**
 * The analysis screens read from a real backend, so they must be honest about
 * why a panel is empty. These components keep that wording in one place.
 */

/** Renders the right message for a CnaError, rather than a generic failure. */
export function AnalysisError({ error, onRetry, compact }) {
  if (!error) return null;

  if (error.offline) {
    return (
      <div className={cn('flex flex-col items-center justify-center px-6 text-center', compact ? 'py-8' : 'py-14')}>
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50">
          <PlugZap className="h-5 w-5 text-amber-600" aria-hidden />
        </div>
        <h3 className="mt-3.5 text-sm font-semibold text-navy-800">Analysis backend not running</h3>
        <p className="mt-1 max-w-md text-[13px] leading-relaxed text-navy-400">
          These screens read live pipeline output — they have no mock fallback, so nothing is shown
          rather than something invented.
        </p>
        <pre className="mt-3 rounded-lg bg-navy-900 px-3 py-2 text-left font-mono text-[11px] text-slate-100">
          ./start.sh
        </pre>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-[13px] font-medium text-teal-700 hover:text-teal-800"
          >
            Retry connection
          </button>
        )}
      </div>
    );
  }

  if (error.forbidden) {
    return (
      <div className={cn('flex flex-col items-center justify-center px-6 text-center', compact ? 'py-8' : 'py-14')}>
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <ShieldX className="h-5 w-5 text-navy-400" aria-hidden />
        </div>
        <h3 className="mt-3.5 text-sm font-semibold text-navy-800">Not permitted for your role</h3>
        <p className="mt-1 max-w-md text-[13px] leading-relaxed text-navy-400">
          {error.message} Switch role in the System view to see access control behave differently.
        </p>
      </div>
    );
  }

  if (error.status === 503) {
    return (
      <div className={cn('flex flex-col items-center justify-center px-6 text-center', compact ? 'py-8' : 'py-14')}>
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          <PackageOpen className="h-5 w-5 text-navy-400" aria-hidden />
        </div>
        <h3 className="mt-3.5 text-sm font-semibold text-navy-800">Capability not installed</h3>
        <p className="mt-1 max-w-md text-[13px] leading-relaxed text-navy-400">{error.message}</p>
      </div>
    );
  }

  return <ErrorState title="Analysis request failed" description={error.message} onRetry={onRetry} compact={compact} />;
}

/** Placeholder rows while a panel loads. */
export function AnalysisSkeleton({ rows = 4, className }) {
  return (
    <div className={cn('space-y-2.5', className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

/**
 * Wraps a panel body: shows the skeleton, then the error, then the children.
 * Keeps every analysis panel behaving the same way.
 */
export function AnalysisPanel({ loading, error, onRetry, rows = 4, empty, children }) {
  if (loading) return <AnalysisSkeleton rows={rows} />;
  if (error) return <AnalysisError error={error} onRetry={onRetry} compact />;
  if (empty) return empty;
  return children;
}

/** The standing responsible-use disclosure. */
export function AnalysisDisclosure({ className }) {
  return (
    <Card className={cn('flex items-start gap-2.5 border-slate-200 bg-slate-50/70 px-4 py-3', className)}>
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-navy-300" aria-hidden />
      <p className="text-[12px] leading-relaxed text-navy-500">{CNA_DISCLOSURE}</p>
    </Card>
  );
}

/** States that the corpus is synthetic — shown wherever source records appear. */
export function SyntheticNotice({ className }) {
  return (
    <p className={cn('text-[12px] leading-relaxed text-navy-400', className)}>{CNA_SYNTHETIC_NOTICE}</p>
  );
}
