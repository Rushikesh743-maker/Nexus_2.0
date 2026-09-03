import { Link } from 'react-router-dom';
import { Share2, MapPin, ShieldAlert, MessagesSquare, ArrowRight, Radar } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { cn } from '@/lib/utils';

/**
 * Direct entry into the case that runs on the live analysis pipeline.
 *
 * This exists because that case was reachable only as one row in a table,
 * several screens deep — the most capable thing in the product was also the
 * hardest to get to. The shortcuts below land on a specific view rather than
 * the case root, so the common destinations cost one click instead of three.
 *
 * The counts are read from the backend, so an offline pipeline shows as
 * offline here rather than as a card promising screens that will not load.
 */
const SHORTCUTS = [
  { to: 'graph', label: 'Network', icon: Share2 },
  { to: 'map', label: 'Map', icon: MapPin },
  { to: 'patterns', label: 'Patterns', icon: ShieldAlert },
  { to: 'ask', label: 'Ask', icon: MessagesSquare },
];

export function AnalysisCaseBand({ investigation, className }) {
  const { data, error, loading } = useCnaResource(() => cnaService.getStats(), []);
  if (!investigation) return null;

  const base = `/investigations/${investigation.id}/analysis`;
  const offline = Boolean(error?.offline);

  return (
    <Card className={cn('overflow-hidden', className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 px-5 py-4">
        <div className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <Badge variant="teal">
              <Radar className="h-3 w-3" aria-hidden />
              Live pipeline
            </Badge>
            <span className="figure text-[10.5px] text-navy-400">{investigation.code}</span>
          </span>

          <Link
            to={base}
            className="mt-2 block text-[15px] font-semibold text-navy-900 transition-colors hover:text-accent"
          >
            {investigation.title}
          </Link>

          {/* What the pipeline currently holds — or why it holds nothing. */}
          <p className="mt-1.5 text-[12px] text-navy-400">
            {loading && !data ? (
              'Reading the pipeline…'
            ) : offline ? (
              <span className="text-amber-700">
                Analysis backend not running — start it with ./start.sh to open these views.
              </span>
            ) : data ? (
              <>
                <span className="figure font-semibold text-navy-700">{data.nodes}</span> entities ·{' '}
                <span className="figure font-semibold text-navy-700">{data.edges}</span> relationships ·{' '}
                <span
                  className="figure font-semibold"
                  style={{ color: data.high_severity ? 'var(--critical)' : 'var(--ink-700)' }}
                >
                  {data.high_severity}
                </span>{' '}
                high-severity findings
              </>
            ) : (
              'Multi-source network analysis'
            )}
          </p>
        </div>

        {/* Land on a view, not on the case root. */}
        <div className="flex flex-wrap items-center gap-2">
          {SHORTCUTS.map((s) => (
            <Link
              key={s.to}
              to={`${base}/${s.to}`}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-[12px] font-medium transition-colors',
                offline
                  ? 'pointer-events-none text-navy-300 opacity-60'
                  : 'text-navy-700 hover:border-line-strong hover:text-navy-900'
              )}
              aria-disabled={offline}
              tabIndex={offline ? -1 : undefined}
            >
              <s.icon className="h-3.5 w-3.5" aria-hidden />
              {s.label}
            </Link>
          ))}
          <Link
            to={base}
            className="inline-flex items-center gap-1.5 rounded-md bg-action px-2.5 py-1.5 text-[12px] font-medium text-action-on transition-colors hover:bg-action-hover"
          >
            Open case
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </div>
      </div>
    </Card>
  );
}
