import { useState } from 'react';
import { Lightbulb, Share2, FileSearch, FileText, Clock, ChevronDown } from 'lucide-react';
import { cn, formatDateTime, truncate } from '@/lib/utils';

/**
 * Interactive evidence chain: Finding → Relationship → Evidence → Source
 * File → Original Record. Each step expands to show its detail. Purely a
 * presentation of linkage provenance — the values come from the mock
 * service layer, no inference is computed in the client.
 *
 * chain: [{ key, label, title, detail?, caption? }]
 */
export function EvidenceChain({ chain = [], className }) {
  const [openKey, setOpenKey] = useState(chain[0]?.key ?? null);

  if (!chain.length) return null;

  return (
    <ol className={cn('space-y-0', className)}>
      {chain.map((step, i) => {
        const isLast = i === chain.length - 1;
        const open = openKey === step.key;
        return (
          <li key={step.key} className="relative flex gap-3">
            {/* connector */}
            {!isLast && (
              <span className="absolute left-[15px] top-9 h-[calc(100%-24px)] w-px bg-slate-200" aria-hidden />
            )}
            <div className="w-full pb-3">
              <button
                type="button"
                onClick={() => setOpenKey(open ? null : step.key)}
                aria-expanded={open}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors',
                  open ? 'border-teal-400 bg-teal-50/50' : 'border-slate-200 bg-white hover:border-teal-300'
                )}
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-navy-500">
                  {step.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-300">
                    {step.label}
                  </span>
                  <span className="block truncate text-[13px] font-medium text-navy-800">{step.title}</span>
                </span>
                <ChevronDown
                  className={cn('h-4 w-4 shrink-0 text-navy-300 transition-transform', open && 'rotate-180')}
                  aria-hidden
                />
              </button>
              {open && (step.detail || step.caption) && (
                <div className="animate-fade-in mx-3 mt-1.5 rounded-lg border border-dashed border-slate-200 bg-slate-50/70 px-3 py-2">
                  {step.detail && <p className="text-[12.5px] leading-relaxed text-navy-600">{step.detail}</p>}
                  {step.caption && <p className="mt-1 font-mono text-[11px] text-navy-300">{step.caption}</p>}
                </div>
              )}
              {!isLast && (
                <span className="ml-[27px] block py-0.5 text-navy-200" aria-hidden>
                  ↓
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Build a finding→record chain from relationship + evidence mock data. */
export function buildChain({ source, target, relationship, evidence }) {
  return [
    {
      key: 'finding',
      label: 'Finding',
      icon: <Lightbulb className="h-4 w-4" aria-hidden />,
      title: `Potential ${relationship.type === 'communication' ? 'communication pattern' : 'association'}`,
      detail: `Automated linking proposed a connection between ${source?.name || 'Entity A'} and ${
        target?.name || 'Entity B'
      }. An analyst reviews every finding before it is relied upon.`,
      caption: 'proposed by link analysis · pending analyst confirmation (mock)',
    },
    {
      key: 'relationship',
      label: 'Relationship',
      icon: <Share2 className="h-4 w-4" aria-hidden />,
      title: `${source?.name || 'A'} ↔ ${target?.name || 'B'}`,
      detail: relationship.label || 'Associated with',
      caption: `analyst confidence ${relationship.strength}%`,
    },
    {
      key: 'evidence',
      label: 'Evidence',
      icon: <FileSearch className="h-4 w-4" aria-hidden />,
      title: evidence ? `${evidence.refNo} — ${truncate(evidence.title, 44)}` : 'No linked evidence recorded',
      detail: evidence?.description || 'Supporting evidence for this connection.',
      caption: evidence ? `status: ${evidence.status.replace(/_/g, ' ')}` : undefined,
    },
    {
      key: 'source',
      label: 'Source File',
      icon: <FileText className="h-4 w-4" aria-hidden />,
      title: evidence?.title || '—',
      detail: evidence ? `Source: ${evidence.source}` : undefined,
      caption: evidence?.hash,
    },
    {
      key: 'record',
      label: 'Original Record',
      icon: <Clock className="h-4 w-4" aria-hidden />,
      title: evidence ? formatDateTime(evidence.collectedAt) : '—',
      detail: 'Earliest original record from which this linkage was derived.',
      caption: evidence?.collectedBy ? `logged by ${evidence.collectedBy}` : undefined,
    },
  ];
}
