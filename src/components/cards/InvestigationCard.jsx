import { ArrowRight, FolderOpen, Share2, Tag } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { INVESTIGATION_STATUS, PRIORITY, caseTypeLabel } from '@/lib/constants';
import { timeAgo } from '@/lib/utils';

/**
 * Investigation summary card — name, case type, status, evidence/entity
 * counts, last update and an explicit Open action.
 */
export function InvestigationCard({ investigation, onClick, className }) {
  const status = INVESTIGATION_STATUS[investigation.status] || INVESTIGATION_STATUS.closed;
  const priority = PRIORITY[investigation.priority] || PRIORITY.low;
  const stats = investigation.stats || { evidence: 0, entities: 0 };

  const open = (e) => {
    e.stopPropagation();
    onClick?.(investigation);
  };

  return (
    <Card
      onClick={() => onClick?.(investigation)}
      className={`flex h-full cursor-pointer flex-col p-4 transition-shadow hover:shadow-md ${className || ''}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-navy-50 px-1.5 py-0.5 font-mono text-[11px] font-medium text-navy-500">
          {investigation.code}
        </span>
        <Badge variant={status.variant} dot>
          {status.label}
        </Badge>
        <Badge variant={priority.variant}>{priority.label}</Badge>
      </div>

      <h3 className="mt-2.5 text-[15px] font-semibold leading-snug text-navy-900">{investigation.title}</h3>
      <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-navy-400">{investigation.summary}</p>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-navy-400">
        <span className="flex items-center gap-1.5 font-medium text-navy-500">
          <Tag className="h-3 w-3 shrink-0" aria-hidden />
          {caseTypeLabel(investigation.caseType)}
        </span>
        <span className="flex items-center gap-1.5">
          <FolderOpen className="h-3 w-3 shrink-0" aria-hidden />
          {stats.evidence} evidence
        </span>
        <span className="flex items-center gap-1.5">
          <Share2 className="h-3 w-3 shrink-0" aria-hidden />
          {stats.entities} entities
        </span>
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 pt-3.5">
        <span className="text-[11px] text-navy-300">Updated {timeAgo(investigation.updatedAt)}</span>
        <button
          type="button"
          onClick={open}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-navy-700 shadow-sm transition-colors hover:border-teal-400 hover:bg-teal-50 hover:text-teal-800"
        >
          Open
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>
    </Card>
  );
}
