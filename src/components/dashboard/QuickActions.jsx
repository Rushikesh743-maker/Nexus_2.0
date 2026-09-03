import { useNavigate } from 'react-router-dom';
import { Upload, Share2, History, ChevronRight, Search } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { openCommandPalette } from '@/components/layout/CommandPalette';

/**
 * Jump list.
 *
 * "Create investigation" is deliberately absent: it already has a primary
 * button in the page header and an entry in the sidebar, and a third copy on
 * the same screen adds a choice without adding a destination.
 *
 * Each row here goes somewhere the header button does not — a case-scoped
 * screen, reached through the case picker so the analyst names the case once
 * instead of navigating twice.
 */
const ACTIONS = [
  { id: 'upload', label: 'Upload evidence', hint: 'Log files against a case', icon: Upload },
  { id: 'network', label: 'Open a link network', hint: 'Entities and relationships', icon: Share2 },
  { id: 'timeline', label: 'Open a timeline', hint: 'Events in sequence', icon: History },
];

export function QuickActions({ onPickCase }) {
  const navigate = useNavigate();

  return (
    <Card>
      <CardHeader title="Jump to" subtitle="Pick a case, land on the screen you wanted." />
      <CardBody className="p-0">
        <ul className="divide-y divide-line-soft">
          {ACTIONS.map((action) => (
            <li key={action.id}>
              <button
                type="button"
                onClick={() => onPickCase(action.id)}
                className="flex w-full items-center gap-3 px-5 py-2.5 text-left transition-colors hover:bg-slate-50"
              >
                <action.icon className="h-4 w-4 shrink-0 text-navy-400" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] font-medium text-navy-800">
                    {action.label}
                  </span>
                  <span className="block truncate text-[11px] text-navy-400">{action.hint}</span>
                </span>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
              </button>
            </li>
          ))}

          {/* Everything else is one keystroke away; say so rather than listing it. */}
          <li>
            <button
              type="button"
              onClick={openCommandPalette}
              className="flex w-full items-center gap-3 px-5 py-2.5 text-left transition-colors hover:bg-slate-50"
            >
              <Search className="h-4 w-4 shrink-0 text-navy-400" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] font-medium text-navy-800">
                  Search everything
                </span>
                <span className="block truncate text-[11px] text-navy-400">
                  Cases, entities, evidence, events
                </span>
              </span>
              <kbd className="figure shrink-0 rounded border border-line px-1.5 py-px text-[10px] text-navy-400">
                ⌘K
              </kbd>
            </button>
          </li>
        </ul>
      </CardBody>
    </Card>
  );
}
