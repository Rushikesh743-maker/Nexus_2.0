import { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, FileText, Clock, X, Loader2, Sparkles } from 'lucide-react';
import { Modal } from '@/components/modals/Modal';
import { Button, IconButton } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Dropzone } from './Dropzone';
import { evidenceService } from '@/services';
import { loadDemoCaseFiles } from '@/mock/mockUploads';
import { useToast } from '@/context/ToastContext';
import { formatFileSize } from '@/lib/utils';
import { cn } from '@/lib/utils';

/**
 * Upload-evidence modal: dropzone → staged file list → per-file lifecycle
 * progress (Uploading → Processing → Processed | Needs review | Failed).
 * All transport/processing is simulated by evidenceService.uploadFiles();
 * nothing here touches the network.
 */
export function UploadEvidenceModal({ open, onClose, investigation, uploadedBy, onUploaded }) {
  const toast = useToast();
  const [staged, setStaged] = useState([]);
  const [states, setStates] = useState({});
  const [uploading, setUploading] = useState(false);

  // Reset when opened/closed.
  useEffect(() => {
    if (open) {
      setStaged([]);
      setStates({});
      setUploading(false);
    }
  }, [open]);

  const addFiles = (files) => {
    setStaged((current) => {
      const existing = new Set(current.map((f) => f.name));
      // The File itself has to survive staging — the ingestion pipeline reads
      // the document's text from it. Dropping it here (as this used to) is why
      // an upload could never populate the network, timeline or map.
      const additions = files
        .map((file) => ({ name: file.name, size: file.size || 0, blob: file instanceof File ? file : null }))
        .filter((file) => !existing.has(file.name));
      if (additions.length) {
        setStates((s) => {
          const next = { ...s };
          additions.forEach((f) => (next[f.name] = { phase: 'pending' }));
          return next;
        });
      }
      return [...current, ...additions];
    });
  };

  const rejectFiles = (names) => {
    toast.warning(
      names.length === 1 ? `${names[0]} is not a supported file type` : `${names.length} files skipped — unsupported types`,
      `Allowed: PDF, DOCX, TXT, CSV, XLSX, JSON, JPG, PNG.`
    );
  };

  const removeStaged = (name) => {
    if (uploading) return;
    setStaged((current) => current.filter((f) => f.name !== name));
  };

  const [loadingDemo, setLoadingDemo] = useState(false);

  const addSamples = async () => {
    setLoadingDemo(true);
    try {
      addFiles(await loadDemoCaseFiles());
    } catch (err) {
      toast.error('Could not load the demo case file', err.message);
    } finally {
      setLoadingDemo(false);
    }
  };

  const startUpload = async () => {
    if (!staged.length) return;
    setUploading(true);
    try {
      await evidenceService.uploadFiles(investigation.id, staged, {
        uploadedBy,
        onProgress: (name, update) => {
          setStates((current) => ({ ...current, [name]: { ...current[name], ...update } }));
          if (update.phase === 'done') onUploaded?.();
        },
      });
    } catch (err) {
      toast.error('Upload failed', err.message);
    } finally {
      setUploading(false);
    }
  };

  const allDone =
    staged.length > 0 && staged.every((f) => states[f.name]?.phase === 'done' || states[f.name]?.phase === 'failed');

  const renderState = (file) => {
    const state = states[file.name] || { phase: 'pending' };
    switch (state.phase) {
      case 'pending':
        return (
          <span className="flex items-center gap-1.5 text-[12px] text-navy-300">
            <Clock className="h-3.5 w-3.5" aria-hidden /> Queued
          </span>
        );
      case 'uploading':
        return (
          <span className="flex w-40 flex-col gap-1">
            <span className="flex justify-between text-[11px] font-medium text-navy-500">
              <span>Uploading</span>
              <span>{state.progress}%</span>
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-slate-100">
              <span
                className="block h-full rounded-full bg-teal-500 transition-[width] duration-150"
                style={{ width: `${state.progress}%` }}
              />
            </span>
          </span>
        );
      case 'processing':
        return (
          <span className="flex flex-col items-end gap-0.5 text-[12px]">
            <span className="flex items-center gap-1.5 font-medium text-sky-700">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> Processing
            </span>
            <span className="text-[11px] text-navy-300">Waiting…</span>
          </span>
        );
      case 'done':
        if (state.status === 'processed')
          return (
            <span className="flex flex-col items-end gap-0.5">
              <span className="flex items-center gap-1.5 text-[12px] font-medium text-emerald-700">
                <CheckCircle2 className="h-4 w-4" aria-hidden /> Processed
              </span>
              {state.extracted && (
                <span className="text-[11px] text-navy-300">
                  {state.extracted.entities} entities · {state.extracted.events} events ·{' '}
                  {state.extracted.locations} locations
                </span>
              )}
            </span>
          );
        if (state.status === 'needs_review')
          return (
            <span className="flex flex-col items-end gap-0.5">
              <span className="flex items-center gap-1.5 text-[12px] font-medium text-amber-700">
                <AlertTriangle className="h-4 w-4" aria-hidden /> Needs review
              </span>
              {state.message && (
                <span className="max-w-[220px] text-right text-[11px] text-navy-300">{state.message}</span>
              )}
            </span>
          );
        if (state.status === 'failed')
          return (
            <span className="flex items-center gap-1.5 text-[12px] font-medium text-rose-700">
              <XCircle className="h-4 w-4" aria-hidden /> Failed
            </span>
          );
        return (
          <span className="flex items-center gap-1.5 text-[12px] font-medium text-teal-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden /> Uploaded
          </span>
        );
      case 'failed':
        return (
          <span className="text-right text-[12px] font-medium text-rose-700">
            Failed
            {state.message && <span className="block text-[11px] font-normal text-navy-300">{state.message}</span>}
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <Modal
      open={open}
      onClose={uploading ? undefined : onClose}
      size="lg"
      title="Upload evidence"
      description={`Files are added to ${investigation.code} · ${investigation.title}`}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={uploading}>
            {allDone ? 'Close' : 'Cancel'}
          </Button>
          {!allDone && (
            <Button onClick={uploading ? undefined : startUpload} loading={uploading} disabled={!uploading && !staged.length}>
              {uploading ? 'Uploading…' : `Upload${staged.length ? ` (${staged.length})` : ''}`}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        <Dropzone onFiles={addFiles} onRejected={rejectFiles} disabled={uploading} />

        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">
            Selected files {staged.length ? `(${staged.length})` : ''}
          </p>
          <button
            type="button"
            onClick={addSamples}
            disabled={uploading || loadingDemo}
            className="flex items-center gap-1 text-[12px] font-medium text-teal-700 transition-colors hover:text-teal-800 disabled:opacity-50"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            {loadingDemo ? 'Loading demo case file…' : 'Add demo case file (missing person bundle)'}
          </button>
        </div>

        {staged.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-200 px-4 py-5 text-center text-[13px] text-navy-300">
            No files selected yet — drop files above or browse.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
            {staged.map((file) => (
              <li key={file.name} className="flex items-center gap-3 px-3.5 py-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-navy-400">
                  <FileText className="h-4 w-4" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-navy-700">{file.name}</span>
                  <span className="text-[11px] text-navy-300">{formatFileSize(file.size)}</span>
                </span>
                {renderState(file)}
                {!uploading && (states[file.name]?.phase ?? 'pending') === 'pending' && (
                  <IconButton icon={X} label={`Remove ${file.name}`} size="iconSm" onClick={() => removeStaged(file.name)} />
                )}
              </li>
            ))}
          </ul>
        )}

        <p className={cn('flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50/70 px-3.5 py-2.5 text-[12px] leading-relaxed text-navy-500')}>
          <span className="mt-0.5">
            <Badge variant="teal">Security</Badge>
          </span>
          <span>
            Evidence files are associated with this investigation. In this frontend-only build nothing leaves your device and no
            local file paths are stored or displayed.
          </span>
        </p>
      </div>
    </Modal>
  );
}
