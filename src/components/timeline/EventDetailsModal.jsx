import { useNavigate } from 'react-router-dom';
import { Eye, MapPin } from 'lucide-react';
import { Modal } from '@/components/modals/Modal';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Avatar } from '@/components/ui/Avatar';
import { EVENT_TYPES, confidenceVariant, confidenceLabel } from '@/lib/constants';
import { formatDate, formatTime } from '@/lib/utils';

/**
 * Event details modal — type, date/time, involved entities, location,
 * linked evidence and a View Evidence deep link. Data comes from the
 * timeline service (mock today).
 */
export function EventDetailsModal({ event, entityById = {}, onClose }) {
  const navigate = useNavigate();
  if (!event) return null;
  const meta = EVENT_TYPES[event.type] || EVENT_TYPES.report;
  const Icon = meta.icon;
  const location = event.locationName || null;

  return (
    <Modal
      open={Boolean(event)}
      onClose={onClose}
      size="sm"
      title="Event Details"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          {event.evidenceId ? (
            <Button
              icon={Eye}
              onClick={() => {
                onClose();
                navigate(`evidence?evidence=${event.evidenceId}`);
              }}
            >
              View Evidence
            </Button>
          ) : (
            <Button icon={Eye} disabled>
              No linked evidence
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span
            style={{ backgroundColor: `${meta.color}14`, color: meta.color }}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          >
            <Icon className="h-5 w-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-snug text-navy-900">{event.title}</p>
            <p className="mt-0.5 flex items-center gap-2 text-[12px] text-navy-400">
              <Badge variant="neutral">{meta.label}</Badge>
              <Badge variant={confidenceVariant(event.confidence)}>{event.confidence}% · {confidenceLabel(event.confidence)}</Badge>
            </p>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Date</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{formatDate(event.datetime)}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Time</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{formatTime(event.datetime)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Location</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">
              {location ? (
                <span className="flex items-center gap-1.5">
                  <MapPin className="h-3.5 w-3.5 text-navy-300" aria-hidden />
                  {location}
                </span>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Entities involved</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {(event.entityIds || []).length === 0 && <span className="text-[13px] text-navy-300">—</span>}
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
            </dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Evidence</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{event.evidenceId ? `Linked record available — open via View Evidence.` : 'No linked record'}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Source</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{event.source}</dd>
          </div>
        </dl>

        {event.description && <p className="text-[13px] leading-relaxed text-navy-500">{event.description}</p>}
      </div>
    </Modal>
  );
}
