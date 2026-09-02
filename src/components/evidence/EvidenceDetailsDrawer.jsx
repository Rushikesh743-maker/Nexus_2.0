import { Download, Trash2, ExternalLink } from 'lucide-react';
import { Drawer } from '@/components/modals/Drawer';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EVIDENCE_TYPES, EVIDENCE_STATUS, FILE_TYPES } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { formatDateTime, formatFileSize, formatDate } from '@/lib/utils';

/**
 * Evidence details side drawer — metadata, automated-extraction results and
 * chain of custody. All data comes from the evidence service (mock today).
 */
export function EvidenceDetailsDrawer({ evidence, onClose, onDelete }) {
  const toast = useToast();
  if (!evidence) return null;

  const typeMeta = EVIDENCE_TYPES[evidence.type] || EVIDENCE_TYPES.document;
  const TypeIcon = typeMeta.icon;
  const statusMeta = EVIDENCE_STATUS[evidence.status] || EVIDENCE_STATUS.uploaded;
  const processed = evidence.status === 'processed';
  const failed = evidence.status === 'failed';

  const download = () => {
    toast.info('File retrieval needs the document service', 'Downloads will work once the backend API is connected.');
  };

  const viewSource = () => {
    toast.info('Source viewer needs the document service', 'In-app preview arrives with the backend integration.');
  };

  return (
    <Drawer
      open={Boolean(evidence)}
      onClose={onClose}
      title={evidence.title}
      subtitle={`${evidence.refNo} · ${evidence.hash || ''}`}
      footer={
        <>
          <Button variant="outline" icon={Download} onClick={download}>
            Download
          </Button>
          <Button variant="danger" icon={Trash2} onClick={() => onDelete?.(evidence)}>
            Delete
          </Button>
          <Button icon={ExternalLink} onClick={viewSource}>
            View Source
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={statusMeta.variant} dot>
            {statusMeta.label}
          </Badge>
          <Badge variant="neutral">{FILE_TYPES[evidence.fileType]?.label || 'File'}</Badge>
          {evidence.category && <Badge variant="teal">{evidence.category}</Badge>}
          {(evidence.tags || []).map((tag) => (
            <Badge key={tag} variant="neutral">
              {tag}
            </Badge>
          ))}
        </div>

        {evidence.description && <p className="text-sm leading-relaxed text-navy-600">{evidence.description}</p>}

        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:grid-cols-2">
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Type</dt>
            <dd className="mt-0.5 flex items-center gap-1.5 text-[13px] text-navy-700">
              <TypeIcon className="h-3.5 w-3.5" style={{ color: typeMeta.color }} aria-hidden />
              {evidence.category || typeMeta.label}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Language</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{evidence.language || '—'}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Status</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{statusMeta.label}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Size</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{formatFileSize(evidence.size)}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Uploaded</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{formatDate(evidence.collectedAt)}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Uploaded by</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{evidence.collectedBy}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-navy-300">Source</dt>
            <dd className="mt-0.5 text-[13px] text-navy-700">{evidence.source}</dd>
          </div>
        </dl>

        {/* Automated extraction results */}
        <section>
          <h3 className="text-[13px] font-semibold text-navy-800">Automated extraction</h3>
          {processed ? (
            <div className="mt-3 grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-slate-200 p-3 text-center">
                <p className="text-xl font-semibold text-navy-900">{evidence.extractedEntities ?? '—'}</p>
                <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-navy-300">Entities</p>
              </div>
              <div className="rounded-xl border border-slate-200 p-3 text-center">
                <p className="text-xl font-semibold text-navy-900">{evidence.extractedEvents ?? '—'}</p>
                <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-navy-300">Events</p>
              </div>
              <div className="rounded-xl border border-slate-200 p-3 text-center">
                <p className="text-xl font-semibold text-navy-900">{evidence.relationshipRefs ?? '—'}</p>
                <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-navy-300">Relationships</p>
              </div>
            </div>
          ) : (
            <p className="mt-2 rounded-lg border border-dashed border-slate-200 px-3.5 py-3 text-[12.5px] leading-relaxed text-navy-400">
              {failed
                ? 'Processing failed for this file. Re-upload it or review the source document.'
                : `Extraction results appear here once automated processing completes — this file is ${statusMeta.label.toLowerCase()}.`}
            </p>
          )}
        </section>

        {/* Chain of custody */}
        <section>
          <h3 className="text-[13px] font-semibold text-navy-800">Chain of custody</h3>
          <ol className="mt-3 space-y-0">
            {(evidence.chainOfCustody || []).map((entry, i, arr) => (
              <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
                {i < arr.length - 1 && <span className="absolute left-[5px] top-4 h-full w-px bg-slate-200" aria-hidden />}
                <span className="relative z-[1] mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-teal-500 bg-white" aria-hidden />
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-navy-700">{entry.action}</p>
                  <p className="mt-0.5 text-[11px] text-navy-300">
                    {entry.by} · {formatDateTime(entry.at)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <p className="text-[11px] leading-relaxed text-navy-300">
          Evidence files are associated with this investigation. This record stores metadata only — no local file paths.
        </p>
      </div>
    </Drawer>
  );
}
