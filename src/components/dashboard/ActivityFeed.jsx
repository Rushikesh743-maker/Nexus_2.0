import { useNavigate } from 'react-router-dom';
import { Upload, UserSearch, Share2, History, FileText, Activity } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/LoadingState';
import { ACTIVITY_TYPES } from '@/lib/constants';
import { timeAgo } from '@/lib/utils';

const ICONS = {
  Upload,
  UserSearch,
  Share2,
  History,
  FileText,
};

const TONES = {
  evidence_added: 'bg-slate-50 text-navy-500',
  entity_match: 'bg-slate-50 text-navy-500',
  relationship_detected: 'bg-slate-50 text-navy-500',
  timeline_updated: 'bg-slate-50 text-navy-500',
  report_generated: 'bg-slate-100 text-navy-500',
};

/**
 * Dashboard activity feed. Items are mock UI events served by
 * investigationService.getRecentActivity() — in production they come from
 * the backend event bus. `hideCase` omits the case chip (case-scoped use).
 */
export function ActivityFeed({ items, isLoading, hideCase = false }) {
  const navigate = useNavigate();

  return (
    <Card>
      <CardHeader title="Recent activity" subtitle="Across your visible cases" />
      <CardBody className="p-0">
        {isLoading ? (
          <div className="space-y-4 px-5 py-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded-lg" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3 w-3/4" />
                  <Skeleton className="h-2.5 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : !items || items.length === 0 ? (
          <EmptyState
            compact
            icon={Activity}
            title="No recent activity"
            description="Case events will appear here as your team works."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {items.map((item) => {
              const Icon = ICONS[ACTIVITY_TYPES[item.type]?.icon] || Activity;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => navigate(item.to)}
                    className="flex w-full items-start gap-3 px-5 py-3 text-left transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-slate-50"
                  >
                    <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${TONES[item.type] || TONES.report_generated}`}>
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-[13px] font-medium text-navy-800">{item.message}</span>
                        <span className="shrink-0 text-[11px] text-navy-300">{timeAgo(item.at)}</span>
                      </span>
                      <span className="mt-0.5 block truncate text-[12px] text-navy-400">{item.detail}</span>
                      {!hideCase && (
                        <span className="mt-1 inline-block rounded bg-navy-50 px-1.5 py-px font-mono text-[10px] font-medium text-navy-500">
                          {item.caseCode}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
