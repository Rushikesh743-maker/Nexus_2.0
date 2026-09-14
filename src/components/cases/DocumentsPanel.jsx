import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, Clock, FileText, Loader2, RefreshCw, Upload,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { caseService, documentService, V1Error } from '@/services/v1';
import { formatDateTime } from '@/lib/utils';

const ACTIVE = new Set(['UPLOADED', 'PROCESSING']);
const POLL_MS = 4000; // real backend status, no invented progress

function StatusBadge({ doc }) {
  if (doc.processing_status === 'PROCESSING') {
    return (
      <Badge variant="warning" dot>
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> processing
      </Badge>
    );
  }
  if (doc.processing_status === 'UPLOADED') {
    return <Badge variant="info" dot><Clock className="h-3 w-3" aria-hidden /> queued</Badge>;
  }
  if (doc.processing_status === 'PROCESSED') {
    return <Badge variant="success" dot><CheckCircle2 className="h-3 w-3" aria-hidden /> processed</Badge>;
  }
  return <Badge variant="danger" dot><AlertTriangle className="h-3 w-3" aria-hidden /> failed</Badge>;
}

/**
 * Case documents: upload, live status, extraction counts, and the path into
 * the review workspace. Polls the real backend while any document is in
 * flight; the UI shows exactly what the API reports.
 */
export function DocumentsPanel({ caseFile }) {
  const navigate = useNavigate();
  const toast = useToast();
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const { data: docs, error, loading, reload } = useCnaResource(
    () => caseService.listDocuments(caseFile.id),
    [caseFile.id]
  );

  const anyActive = (docs || []).some((d) => ACTIVE.has(d.processing_status));

  // Poll the real status while work is in flight (uploads + processing).
  useEffect(() => {
    if (!anyActive) return undefined;
    const t = setInterval(() => { reload(); }, POLL_MS);
    return () => clearInterval(t);
  }, [anyActive, reload]);

  const handleUpload = useCallback(async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const doc = await documentService.uploadDocument(caseFile.id, file);
      toast.success(`Uploaded ${doc.filename}`, 'Extraction starts automatically.');
      reload();
    } catch (e) {
      toast.error(e.message || 'Upload failed.');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }, [caseFile.id, reload, toast]);

  const handleRetry = useCallback(async (doc) => {
    try {
      await documentService.processDocument(doc.id);
      toast.info(`Reprocessing ${doc.filename}…`);
      reload();
    } catch (e) {
      toast.error(e.message || 'Could not reprocess the document.');
    }
  }, [reload, toast]);

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-[14px] font-semibold text-navy-900">Documents</h2>
          <p className="figure text-[11px] text-navy-400">
            PDF, TXT or CSV · processed in the backend · reviewed before anything reaches the case graph
          </p>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,.csv"
          className="hidden"
          onChange={(e) => handleUpload(e.target.files?.[0])}
        />
        <Button
          variant="outline"
          size="sm"
          icon={Upload}
          loading={uploading}
          onClick={() => fileRef.current?.click()}
        >
          {uploading ? 'Uploading…' : 'Upload document'}
        </Button>
      </div>

      {loading && !docs ? (
        <div className="flex items-center gap-2 px-5 py-10 text-[13px] text-navy-400">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading documents…
        </div>
      ) : error && !docs ? (
        <EmptyState
          icon={AlertTriangle}
          title={error instanceof V1Error && error.offline ? 'Backend unreachable' : 'Documents unavailable'}
          description={error.offline
            ? 'Start the backend (python3 backend/run.py) and retry.'
            : error.message}
          action={<Button variant="outline" size="sm" icon={RefreshCw} onClick={reload}>Retry</Button>}
          compact
        />
      ) : !docs || docs.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload a PDF, TXT or CSV file. It is stored, extracted, and the resulting entity candidates are queued for investigator review."
          action={
            <Button variant="outline" size="sm" icon={Upload} loading={uploading} onClick={() => fileRef.current?.click()}>
              Upload the first document
            </Button>
          }
          compact
        />
      ) : (
        <ul className="divide-y divide-line">
          {docs.map((doc) => (
            <li key={doc.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
              <div className="min-w-0 flex-1 basis-52">
                <p className="truncate text-[13px] font-medium text-navy-800" title={doc.filename}>
                  {doc.filename}
                </p>
                <p className="figure text-[10.5px] text-navy-400">
                  {doc.file_type?.toUpperCase() || '—'} · {doc.file_size != null ? `${(doc.file_size / 1024).toFixed(1)} KB` : '—'}
                  {' · uploaded '}{formatDateTime(doc.uploaded_at)}
                  {doc.uploaded_by_name ? ` by ${doc.uploaded_by_name}` : ''}
                </p>
                {doc.processing_status === 'FAILED' && doc.processing_error && (
                  <p className="mt-1 text-[11.5px] text-rose-600" title={doc.processing_error}>
                    {doc.processing_error}
                  </p>
                )}
              </div>

              <StatusBadge doc={doc} />

              {doc.processing_status === 'PROCESSED' && (
                <span className="figure text-[11px] text-navy-500">
                  {doc.extracted_entities} candidates
                  {doc.pending_review > 0 && <span className="text-amber-600"> · {doc.pending_review} to review</span>}
                  {` · ${doc.extracted_relationships} links`}
                </span>
              )}

              <div className="flex items-center gap-2">
                {doc.processing_status === 'FAILED' && (
                  <Button variant="outline" size="sm" icon={RefreshCw} onClick={() => handleRetry(doc)}>
                    Retry
                  </Button>
                )}
                <Button
                  variant={doc.pending_review > 0 ? 'accent' : 'ghost'}
                  size="sm"
                  onClick={() => navigate(`/cases/${caseFile.id}/documents/${doc.id}`)}
                >
                  Review
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
