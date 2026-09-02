import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, UserSearch, AlertTriangle, Share2, FileText, CheckCheck } from 'lucide-react';
import { analysisService } from '@/services';
import { timeAgo } from '@/lib/utils';

const ICONS = { Upload, UserSearch, AlertTriangle, Share2, FileText };

/**
 * Notification feed (mock, via analysisService). Rendered inside the topbar
 * bell dropdown — mounts only while open.
 */
export function NotificationsDropdown() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [readIds, setReadIds] = useState(() => new Set());

  useEffect(() => {
    let active = true;
    analysisService
      .getNotifications()
      .then((d) => active && setData(d))
      .catch(() => active && setData({ items: [], unread: 0 }));
    return () => {
      active = false;
    };
  }, []);

  const unread = data ? data.items.filter((n) => !readIds.has(n.id)).slice(0, data.unread).length : 0;

  return (
    <div className="w-[300px]">
      <div className="flex items-center justify-between border-b border-slate-100 px-3.5 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">
          {unread > 0 ? `${unread} new update${unread === 1 ? '' : 's'}` : 'Notifications'}
        </p>
        {unread > 0 && (
          <button
            type="button"
            onClick={() => setReadIds(new Set(data.items.map((n) => n.id)))}
            className="flex items-center gap-1 text-[11px] font-medium text-teal-700 hover:text-teal-800"
          >
            <CheckCheck className="h-3 w-3" aria-hidden /> Mark all read
          </button>
        )}
      </div>
      {!data ? (
        <p className="px-3.5 py-4 text-[12px] text-navy-300">Loading…</p>
      ) : (
        <ul className="max-h-[320px] overflow-y-auto scrollbar-thin">
          {data.items.map((n) => {
            const Icon = ICONS[n.icon] || Share2;
            const isUnread = !readIds.has(n.id) && data.items.indexOf(n) < data.unread;
            return (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => navigate(n.to)}
                  className="flex w-full items-start gap-2.5 px-3.5 py-2.5 text-left transition-colors hover:bg-slate-50"
                >
                  <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${isUnread ? 'bg-teal-50 text-teal-700' : 'bg-slate-100 text-navy-400'}`}>
                    <Icon className="h-3.5 w-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className={`truncate text-[12.5px] ${isUnread ? 'font-semibold text-navy-800' : 'font-medium text-navy-600'}`}>{n.title}</span>
                      <span className="shrink-0 text-[10.5px] text-navy-300">{timeAgo(n.at)}</span>
                    </span>
                    <span className="mt-0.5 block truncate text-[11.5px] text-navy-400">{n.detail}</span>
                  </span>
                  {isUnread && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-500" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <p className="border-t border-slate-100 px-3.5 py-2 text-[10.5px] text-navy-300">Mock feed — alerts arrive from backend services in production.</p>
    </div>
  );
}
