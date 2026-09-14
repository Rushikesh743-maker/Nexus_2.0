import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, RefreshCw, Upload, Loader2, AlertTriangle } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useToast } from '@/context/ToastContext';
import { useCnaResource } from '@/hooks/useCnaResource';
import { documentService, V1Error } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { formatDateTime } from '@/lib/utils';

/**
 * Case documents — the upload & processing surface of the case workspace.
 *
 * Everything is real backend state: documents walk UPLOADED -> PROCESSING
 * -> PROCESSED | FAILED through async background work, and the page polls
 * the per-document status endpoint while any document is in flight. There
 * is no progress percentage — only the persisted state and, on failure,
 * the exact reason plus a working RETRY.
 */

const STATUS_STYLE = {
  UPLOADED: 'bg-slate-100 text-navy-600 border-line',
  PROCESSING: 'bg-sky-50 text-sky-700 border-sky-200',
  PROCESSED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  REVIEW_REQUIRED: 'bg-amber-50 text-amber-700 border-amber-200',
  FAILED: 'bg-rose-50 text-rose-700 border-rose-200',
  PENDING: 'bg-slate-100 text-navy-600 border-line',
};

function StatusPill({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${STATUS_STYLE[status] || STATUS_STYLE.PENDING}`}>
      {status}
    </span>
  );
}

export function CaseDocumentsPage() {
  const { caseFile: c } = useCaseFile();
  const toast = useToast();
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => documentService.listCaseDocuments(c.id), [c.id]),
    [c.id]
  );

  const inFlight = (data || []).some(
    (d) => d.processing_status === 'PROCESSING' || d.processing_status === 'UPLOADED'
  );

  // While work is in flight, refresh the list on an interval so the page
  // reflects real persisted state as each document settles.
  useEffect(() => {
    if (!inFlight) return undefined;
    const t = setInterval(() => reload(), 2500);
    return () => clearInterval(t);
  }, [inFlight, reload]);

  const onUpload = async (files) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of files) {
        await documentService.uploadDocument(c.id, file);
      }
      toast.success(`${files.length} document(s) uploaded — processing started.`);
      reload();
    } catch (err) {
      if (err instanceof V1Error && err.code === 'DOCUMENT_DUPLICATE') {
        toast.error('One or more files already exist in this case (same content).');
      } else {
        toast.error(err.message || 'Upload failed.');
      }
      reload();
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const onRetry = async (doc) => {
    try {
      await documentService.processDocument(doc.id);
      toast.info(`Reprocessing ${doc.filename}…`);
      reload();
    } catch (err) {
      toast.error(err.message || 'Retry failed.');
    }
  };

  const docs = data || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-display text-[17px] text-navy-900">Documents</h2>
          <p className="text-[12px] text-navy-400">
            {docs.length} in this case · processing runs asynchronously; each document reports its real persisted state.
          </p>
        </div>
        <Button
          icon={uploading ? Loader2 : Upload}
          loading={uploading}
          onClick={() => fileRef.current?.click()}
        >
          Upload document
        </Button>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.txt,.csv,.json"
          className="hidden"
          onChange={(e) => onUpload([...e.target.files])}
        />
      </div>

      {loading && !docs.length && <PageLoader label="Loading documents…" />}
      {error && !docs.length && (
        <ErrorState title="Documents unavailable" description={error.message} onRetry={reload} />
      )}

      {docs.length > 0 && (
        <Card>
          <CardHeader
            title="Case document record"
            subtitle="PDF, TXT, CSV and JSON accepted — content-hashed, deduplicated per case"
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12.5px]">
              <thead>
                <tr className="border-b border-line text-[10.5px] uppercase tracking-[0.08em] text-navy-300">
                  <th className="px-4 py-2 font-medium">Document</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Language</th>
                  <th className="px-3 py-2 font-medium">Extracted</th>
                  <th className="px-3 py-2 font-medium">Pending review</th>
                  <th className="px-3 py-2 font-medium">Uploaded</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {docs.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-50/60">
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/cases/${c.id}/documents/${d.id}`}
                        className="flex items-center gap-2 font-medium text-navy-800 hover:text-navy-950"
                      >
                        <FileText className="h-3.5 w-3.5 text-navy-300" aria-hidden />
                        {d.filename}
                      </Link>
                      <p className="figure mt-0.5 pl-5.5 text-[10.5px] text-navy-300">
                        doc {d.id} · {d.file_type?.toUpperCase()}
                        {d.language ? ` · ${d.language.toUpperCase()}` : ''}
                      </p>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusPill status={d.processing_status} />
                      {d.processing_status === 'PROCESSING' && (
                        <Loader2 className="ml-1.5 inline h-3 w-3 animate-spin text-sky-500" aria-hidden />
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-navy-500">
                      {d.language ? (
                        <>
                          {d.language.toUpperCase()}
                          {typeof d.language_confidence === 'number' && (
                            <span className="figure text-navy-300"> {(d.language_confidence * 100).toFixed(0)}%</span>
                          )}
                        </>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="figure text-navy-700">{d.extracted_entities ?? 0}</span>
                      <span className="text-navy-300"> entities</span>{' '}
                      <span className="figure text-navy-700">{d.extracted_relationships ?? 0}</span>
                      <span className="text-navy-300"> rels</span>
                    </td>
                    <td className="px-3 py-2.5">
                      {d.pending_review > 0 ? (
                        <Badge variant="warning">{d.pending_review} pending</Badge>
                      ) : (
                        <span className="text-navy-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-navy-400">{formatDateTime(d.uploaded_at)}</td>
                    <td className="px-4 py-2.5 text-right">
                      {d.processing_status === 'FAILED' && (
                        <Button variant="outline" size="sm" icon={RefreshCw} onClick={() => onRetry(d)}>
                          Retry
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {docs.some((d) => d.processing_status === 'FAILED') && (
            <div className="flex items-start gap-2 border-t border-line-soft bg-rose-50/50 px-4 py-2.5">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" aria-hidden />
              <p className="text-[11.5px] text-rose-700">
                A failed document does not fail the case — open it for the exact reason and use Retry.
              </p>
            </div>
          )}
        </Card>
      )}

      {data && docs.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload PDF, TXT, CSV or JSON documents to start extraction. The investigator only uploads — processing, extraction and review happen through the pipeline."
        />
      )}
    </div>
  );
}
