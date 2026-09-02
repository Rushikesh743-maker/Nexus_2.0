import { EVENT_TYPES, confidenceVariant, confidenceLabel } from '@/lib/constants';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { formatDate, formatTime, cn } from '@/lib/utils';

/**
 * Vertical event timeline grouped by day.
 * events: sorted newest-first; entityById: map for participant chips;
 * onEventClick(event) makes rows clickable for the details modal.
 */
export function EventTimeline({ events = [], entityById = {}, onEventClick }) {
  const groups = [];
  events.forEach((event) => {
    const key = formatDate(event.datetime);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.events.push(event);
    else groups.push({ key, events: [event] });
  });

  return (
    <div className="space-y-7">
      {groups.map((group) => (
        <section key={group.key}>
          <h3 className="sticky top-0 z-[1] -mx-1 bg-white/95 px-1 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-navy-300">
            {group.key}
          </h3>
          <ol className="mt-1 space-y-0">
            {group.events.map((event, i) => {
              const meta = EVENT_TYPES[event.type] || EVENT_TYPES.report;
              const Icon = meta.icon;
              const isLast = i === group.events.length - 1;
              return (
                <li key={event.id} className="relative flex gap-4 pb-6 last:pb-0">
                  {!isLast && <span className="absolute left-[17px] top-10 h-full w-px bg-slate-200" aria-hidden />}
                  <span
                    style={{ backgroundColor: `${meta.color}14`, color: meta.color }}
                    className="relative z-[1] flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                    title={meta.label}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <button
                      type="button"
                      onClick={() => onEventClick?.(event)}
                      className="w-full rounded-lg text-left transition-colors hover:bg-slate-50"
                    >
                      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                        <h4 className="text-sm font-semibold text-navy-800">{event.title}</h4>
                        <time className="shrink-0 text-[11px] font-medium text-navy-300">{formatTime(event.datetime)}</time>
                      </div>
                      {event.description && (
                        <p className="mt-1 text-[13px] leading-relaxed text-navy-500">{event.description}</p>
                      )}
                    </button>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {event.locationName && (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-navy-500">
                          {event.locationName}
                        </span>
                      )}
                      {(event.entityIds || []).map((id) => {
                        const ent = entityById[id];
                        if (!ent) return null;
                        return (
                          <span
                            key={id}
                            className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white py-0.5 pl-0.5 pr-2 text-[11px] font-medium text-navy-600"
                          >
                            <Avatar name={ent.name} size="xs" />
                            {ent.name}
                          </span>
                        );
                      })}
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-navy-300">
                      <span>Source: {event.source}</span>
                      <span aria-hidden>·</span>
                      <Badge variant={confidenceVariant(event.confidence)} className={cn('cursor-default')}>
                        {event.confidence}% · {confidenceLabel(event.confidence)}
                      </Badge>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
