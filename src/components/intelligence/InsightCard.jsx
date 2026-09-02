import { Check } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { ConfidenceMeter } from './ConfidenceMeter';
import { INSIGHT_CATEGORIES, INSIGHT_STATUS } from '@/lib/constants';
import { formatDate } from '@/lib/utils';

export function InsightCard({ insight, entityById = {}, onMarkReviewed, busy = false }) {
  const category = INSIGHT_CATEGORIES[insight.category] || INSIGHT_CATEGORIES.pattern;
  const status = INSIGHT_STATUS[insight.status] || INSIGHT_STATUS.new;
  const linked = (insight.linkedEntityIds || []).map((id) => entityById[id]).filter(Boolean);

  return (
    <Card className="flex h-full flex-col">
      <CardBody className="flex flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={category.variant}>{category.label}</Badge>
          <Badge variant={status.variant} dot={insight.status === 'new'}>
            {status.label}
          </Badge>
          <span className="ml-auto text-[11px] text-navy-300">{formatDate(insight.createdAt)}</span>
        </div>
        <div>
          <h3 className="text-sm font-semibold leading-snug text-navy-900">{insight.title}</h3>
          <p className="mt-1.5 text-[13px] leading-relaxed text-navy-500">{insight.summary}</p>
        </div>
        {linked.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {linked.map((ent) => (
              <span
                key={ent.id}
                className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white py-0.5 pl-0.5 pr-2 text-[11px] font-medium text-navy-600"
                title={ent.name}
              >
                <Avatar name={ent.name} size="xs" />
                {ent.name}
              </span>
            ))}
          </div>
        )}
        <div className="mt-auto space-y-3 pt-1">
          <ConfidenceMeter value={insight.confidence} />
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[11px] text-navy-300">{insight.source}</span>
            {insight.status === 'new' && onMarkReviewed && (
              <Button variant="ghost" size="sm" icon={Check} onClick={() => onMarkReviewed(insight)} disabled={busy}>
                Mark reviewed
              </Button>
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
