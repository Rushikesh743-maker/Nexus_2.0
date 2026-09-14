import { useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { User, Phone, Car, Building2, MapPin, Wallet, Briefcase, Clock, Tag } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

const TYPE_META = {
  person: { label: 'Persons', icon: User },
  phone: { label: 'Phones', icon: Phone },
  vehicle: { label: 'Vehicles', icon: Car },
  organization: { label: 'Organizations', icon: Building2 },
  location: { label: 'Locations', icon: MapPin },
  account: { label: 'Accounts', icon: Wallet },
  case_reference: { label: 'Case references', icon: Briefcase },
  event: { label: 'Events', icon: Clock },
  other: { label: 'Other', icon: Tag },
};
const ORDER = ['person', 'phone', 'vehicle', 'organization', 'location', 'account', 'case_reference', 'event', 'other'];

/**
 * Case entities — the CONFIRMED entities of this one case, grouped by
 * type. Candidates are not listed here (they wait in the Review queue);
 * every name, alias and confidence shown is what the acceptance workflow
 * persisted. "Show in graph" deep-links the graph tab to this entity.
 */
export function CaseEntitiesPage() {
  const { caseFile: c } = useCaseFile();
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => caseService.listEntities(c.id), [c.id]),
    [c.id]
  );

  const byType = useMemo(() => {
    const map = {};
    for (const e of data || []) {
      const key = TYPE_META[e.entity_type] ? e.entity_type : 'other';
      (map[key] = map[key] || []).push(e);
    }
    return map;
  }, [data]);

  if (loading && !data) return <PageLoader label="Loading entities…" />;
  if (error && !data) return <ErrorState title="Entities unavailable" description={error.message} onRetry={reload} />;

  const total = data?.length ?? 0;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-display text-[17px] text-navy-900">Entities</h2>
        <p className="text-[12px] text-navy-400">
          {total} confirmed in this case · candidates awaiting a decision live on the{' '}
          <Link to={`/cases/${c.id}/review`} className="font-medium text-navy-600 hover:text-navy-900">Review</Link> tab.
        </p>
      </div>

      {total === 0 ? (
        <EmptyState
          icon={User}
          title="No confirmed entities yet"
          description="Process a document and confirm its extracted candidates — confirmed entities will appear here, grouped by type."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {ORDER.filter((t) => byType[t]?.length).map((t) => {
            const meta = TYPE_META[t];
            return (
              <Card key={t}>
                <CardHeader
                  title={meta.label}
                  actions={<Badge variant="default">{byType[t].length}</Badge>}
                />
                <ul className="divide-y divide-line-soft">
                  {byType[t].map((e) => {
                    const aliases = e.metadata?.aliases || [];
                    return (
                      <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                        <div className="min-w-0">
                          <p className="text-[13px] font-medium text-navy-800">{e.canonical_name}</p>
                          {aliases.length > 0 && (
                            <p className="mt-0.5 truncate text-[11px] text-navy-400">
                              also known as {aliases.slice(0, 4).join(', ')}
                              {aliases.length > 4 && ` +${aliases.length - 4}`}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="figure text-[10px] text-navy-300">{formatDateTime(e.created_at)}</span>
                          <Link
                            to={`/cases/${c.id}/entities/${e.id}`}
                            className="text-[11.5px] font-medium text-navy-500 hover:text-navy-900"
                          >
                            Profile
                          </Link>
                          <Link
                            to={`/cases/${c.id}/graph?entity=${e.id}`}
                            className="text-[11.5px] font-medium text-navy-500 hover:text-navy-900"
                          >
                            Show in graph →
                          </Link>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
