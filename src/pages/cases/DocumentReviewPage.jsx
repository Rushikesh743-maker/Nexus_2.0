import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowLeft, Check, Clock, GitMerge, Link2, Loader2,
  RefreshCw, X,
} from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { documentService, V1Error } from '@/services/v1';
import { formatDateTime } from '@/lib/utils';

const TYPE_VARIANT = {
  person: 'teal', phone: 'info', vehicle: 'violet', location: 'success',
  account: 'neutral', organization: 'warning', case: 'danger',
  event: 'neutral', document: 'neutral',
};

/** "line 4" / "row 2 · column caller_name" / "page 1" — human provenance. */
function provenanceText(loc) {
  if (!loc) return null;
  const parts = [];
  if (loc.line != null) parts.push(`line ${loc.line}`);
  if (loc.row != null) parts.push(`row ${loc.row}`);
  if (loc.column) parts.push(`column “${loc.column}”`);
  if (loc.page != null) parts.push(`page ${loc.page}`);
  return parts.length ? parts.join(' · ') : null;
}

/**
 * Investigator review workspace for one document:
 *   matches  → entity candidates → relationship candidates.
 * Acceptance is the only path that writes to the confirmed case data;
 * every decision is explicit and audited by the backend.
 */
export function DocumentReviewPage() {
  const { caseId, documentId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [actingId, setActingId] = useState(null);
  const {
    data: extraction,
    error,
    loading,
    reload,
  } = useCnaResource(
    () => documentService.getExtraction(Number(documentId)),
    [documentId]
  );

  const doc = extraction?.document || null;
  const status = doc?.processing_status || null;
  const inFlight = status === 'UPLOADED' || status === 'PROCESSING';

  // While the document is still processing, poll the real status and stop
  // as soon as it settles (PROCESSED or FAILED).
  useEffect(() => {
    if (!inFlight) return undefined;
    const t = setInterval(() => { reload(); }, 4000);
    return () => clearInterval(t);
  }, [inFlight, reload]);

  const runAction = useCallback(async (label, fn) => {
    setActingId(label);
    try {
      await fn();
      reload();
      return true;
    } catch (e) {
      toast.error(e.message || 'Action failed.');
      return false;
    } finally {
      setActingId(null);
    }
  }, [reload, toast]);

  const pendingMatches = useMemo(
    () => (extraction?.entities || []).filter((c) => c.match?.status === 'PENDING'),
    [extraction]
  );
  const candidates = useMemo(
    () => (extraction?.entities || []).filter((c) => !c.match || c.match.status !== 'PENDING'),
    [extraction]
  );
  const relationships = useMemo(() => extraction?.relationships || [], [extraction]);

  if (loading && !extraction) {
    return (
      <div className="flex items-center gap-2 py-14 text-[13px] text-navy-400">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading document…
      </div>
    );
  }

  if (error && !extraction) {
    const offline = error instanceof V1Error && error.offline;
    return (
      <ErrorState
        title={offline ? 'Backend unreachable' : 'Document not available'}
        description={offline
          ? 'Start the backend (python3 backend/run.py) and retry.'
          : error.message}
        onRetry={reload}
        action={<Button variant="outline" icon={ArrowLeft} onClick={() => navigate(`/cases/${caseId}/evidence`)}>Back to evidence</Button>}
      />
    );
  }

  if (status === 'FAILED') {
    return (
      <div className="space-y-4">
        <BackLink caseId={caseId} filename={doc.filename} />
        <Card>
          <div className="px-5 py-6">
            <ErrorState
              compact
              title="Processing failed"
              description={doc.processing_error || 'The document could not be processed.'}
              onRetry={() => runAction('retry', () => documentService.processDocument(doc.id))}
              action={actingId === 'retry' ? <span className="figure text-[11px] text-navy-400">retrying…</span> : undefined}
            />
          </div>
        </Card>
      </div>
    );
  }

  if (inFlight) {
    return (
      <div className="space-y-4">
        <BackLink caseId={caseId} filename={doc.filename} />
        <Card>
          <div className="flex flex-col items-center px-6 py-14 text-center">
            <Loader2 className="h-6 w-6 animate-spin text-navy-300" aria-hidden />
            <h3 className="mt-4 text-sm font-semibold text-navy-800">
              {status === 'PROCESSING' ? 'Extracting entities…' : 'Queued for extraction'}
            </h3>
            <p className="mt-1 max-w-sm text-[13px] text-navy-400">
              The backend is reading the document and proposing entity and relationship candidates.
              This page refreshes automatically — nothing is invented or pre-filled.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  const summary = extraction.summary || {};
  const nothingToReview =
    candidates.length === 0 && relationships.length === 0 && pendingMatches.length === 0;

  return (
    <div className="space-y-5">
      <BackLink caseId={caseId} filename={doc.filename} />

      {summary.original_text != null && summary.original_text !== '' && (
        <Card>
          <div className="border-b border-line px-5 py-4">
            <h2 className="text-[14px] font-semibold text-navy-900">Original document text</h2>
            <p className="figure mt-1 text-[11px] text-navy-400">
              Verbatim content as uploaded — never modified by extraction
              {summary.language && <> · detected {summary.language}</>}
              {summary.language_confidence != null && <> · {Math.round(summary.language_confidence * 100)}% confidence</>}
            </p>
          </div>
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-[12px] leading-relaxed text-navy-700">
            {summary.original_text}
          </pre>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="font-display text-[22px] leading-tight text-navy-900">{doc.filename}</h1>
        <Badge variant="success" dot>processed</Badge>
        <span className="figure text-[11px] text-navy-400">
          {summary.entities} candidates · {summary.relationships} link proposals
          {summary.pending > 0 && <span className="text-amber-600"> · {summary.pending} awaiting review</span>}
          {' · '}{summary.accepted} accepted · {summary.rejected} rejected
        </span>
      </div>

      {nothingToReview ? (
        <Card>
          <EmptyState
            icon={Check}
            title="Nothing pending for this document"
            description="All extracted candidates have been reviewed. Accepted items are already in the case graph, timeline and evidence register."
            compact
          />
        </Card>
      ) : (
        <>
          {/* 1 — match suggestions */}
          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="flex items-center gap-2 text-[14px] font-semibold text-navy-900">
                <GitMerge className="h-4 w-4 text-navy-400" aria-hidden /> Suggested matches
              </h2>
              <p className="figure text-[11px] text-navy-400">
                Candidates that probably refer to an entity already confirmed in this case. Accepting folds the
                candidate into the existing entity; rejecting keeps it independent.
              </p>
            </div>
            {pendingMatches.length === 0 ? (
              <EmptyState compact icon={Check} title="No pending matches"
                description="Every candidate is either new or already matched." />
            ) : (
              <ul className="divide-y divide-line">
                {pendingMatches.map((cand) => (
                  <li key={cand.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
                    <div className="min-w-0 flex-1 basis-64">
                      <p className="text-[13px] text-navy-800">
                        <span className="font-medium">{cand.candidate_name}</span>
                        <span className="mx-2 text-navy-300">→</span>
                        <span className="font-medium text-teal-700">{cand.match.existing_entity_name}</span>
                      </p>
                      <p className="figure mt-0.5 text-[10.5px] text-navy-400">
                        similarity {Math.round((cand.match.similarity || 0) * 100)}%
                        {cand.match.reasons?.length > 0 && <> · {cand.match.reasons.join(' · ')}</>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm" variant="outline"
                        icon={X}
                        loading={actingId === `match-reject-${cand.match.id}`}
                        onClick={() => runAction(`match-reject-${cand.match.id}`,
                          async () => { await documentService.rejectMatch(doc.id, cand.match.id); toast.info(`Match rejected — “${cand.candidate_name}” stays independent.`); })}
                      >
                        Not a match
                      </Button>
                      <Button
                        size="sm" variant="primary"
                        icon={Check}
                        loading={actingId === `match-accept-${cand.match.id}`}
                        onClick={() => runAction(`match-accept-${cand.match.id}`,
                          async () => { await documentService.acceptMatch(doc.id, cand.match.id); toast.success(`“${cand.candidate_name}” matched to “${cand.match.existing_entity_name}”.`); })}
                      >
                        Accept match
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* 2 — entity candidates */}
          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="flex items-center gap-2 text-[14px] font-semibold text-navy-900">
                <Clock className="h-4 w-4 text-navy-400" aria-hidden /> Entity candidates
              </h2>
              <p className="figure text-[11px] text-navy-400">
                Extracted from the document with provenance. Accepting adds a confirmed entity to the case;
                rejecting preserves the candidate for the audit trail.
              </p>
            </div>
            {candidates.length === 0 ? (
              <EmptyState compact icon={Check} title="No entity candidates" />
            ) : (
              <ul className="divide-y divide-line">
                {candidates.map((cand) => (
                  <CandidateRow
                    key={cand.id}
                    cand={cand}
                    docId={doc.id}
                    actingId={actingId}
                    onAccept={() => runAction(`cand-${cand.id}`,
                      async () => { await documentService.acceptCandidate(doc.id, cand.id); toast.success(`“${cand.candidate_name}” accepted.`); })}
                    onReject={() => runAction(`cand-rej-${cand.id}`,
                      async () => { await documentService.rejectCandidate(doc.id, cand.id); toast.info(`“${cand.candidate_name}” rejected.`); })}
                    onDefer={() => runAction(`cand-def-${cand.id}`,
                      async () => { await documentService.deferCandidate(doc.id, cand.id); toast.info(`“${cand.candidate_name}” marked for later.`); })}
                  />
                ))}
              </ul>
            )}
          </Card>

          {/* 3 — relationship candidates */}
          <Card>
            <div className="border-b border-line px-5 py-4">
              <h2 className="flex items-center gap-2 text-[14px] font-semibold text-navy-900">
                <Link2 className="h-4 w-4 text-navy-400" aria-hidden /> Relationship proposals
              </h2>
              <p className="figure text-[11px] text-navy-400">
                Proposed only where the document states the link. Both endpoint entities must be accepted
                before the relationship can be confirmed.
              </p>
            </div>
            {relationships.length === 0 ? (
              <EmptyState compact icon={Check} title="No relationship proposals" />
            ) : (
              <ul className="divide-y divide-line">
                {relationships.map((rel) => (
                  <li key={rel.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
                    <div className="min-w-0 flex-1 basis-72">
                      <p className="text-[13px] text-navy-800">
                        <span className="font-medium">{rel.source_name || '—'}</span>
                        <span className="mx-2 inline-flex"><Badge variant="info">{rel.relationship_type}</Badge></span>
                        <span className="font-medium">{rel.target_name || '—'}</span>
                      </p>
                      <p className="figure mt-0.5 text-[10.5px] text-navy-400">
                        confidence {rel.confidence != null ? `${Math.round(rel.confidence * 100)}%` : '—'}
                        {' · '}{provenanceText(rel.source_location) || '—'}
                      </p>
                      {rel.source_snippet && (
                        <p className="mt-1 line-clamp-2 max-w-2xl text-[11px] italic text-navy-400">
                          “{rel.source_snippet}”
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm" variant="outline" icon={X}
                        disabled={rel.status !== 'PENDING'}
                        loading={actingId === `rel-rej-${rel.id}`}
                        onClick={() => runAction(`rel-rej-${rel.id}`,
                          async () => { await documentService.rejectRelationship(doc.id, rel.id); toast.info('Relationship rejected.'); })}
                      >
                        {rel.status === 'REJECTED' ? 'Rejected' : 'Reject'}
                      </Button>
                      <Button
                        size="sm" variant="primary" icon={Check}
                        disabled={!rel.endpoints_confirmed || rel.status !== 'PENDING'}
                        loading={actingId === `rel-${rel.id}`}
                        title={rel.endpoints_confirmed ? undefined : 'Accept both endpoint entities first'}
                        onClick={() => runAction(`rel-${rel.id}`,
                          async () => { await documentService.acceptRelationship(doc.id, rel.id); toast.success(`Relationship ${rel.relationship_type} confirmed.`); })}
                      >
                        {rel.status === 'ACCEPTED' ? 'Confirmed' : 'Accept'}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function BackLink({ caseId, filename }) {
  return (
    <Link
      to={`/cases/${caseId}/evidence`}
      className="inline-flex items-center gap-1.5 text-[12px] font-medium text-navy-400 transition-colors hover:text-navy-700"
    >
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Evidence · {filename}
    </Link>
  );
}

function CandidateRow({ cand, docId, actingId, onAccept, onReject, onDefer }) {
  const reviewed = cand.status === 'ACCEPTED' || cand.status === 'REJECTED';
  const loc = provenanceText(cand.source_location);
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
      <div className="min-w-0 flex-1 basis-64">
        <p className="text-[13px] text-navy-800">
          <span className="font-medium">{cand.candidate_name}</span>{' '}
          <Badge variant={TYPE_VARIANT[cand.entity_type] || 'neutral'}>{cand.entity_type}</Badge>
          {cand.status === 'ACCEPTED' && <Badge variant="success">accepted</Badge>}
          {cand.status === 'REJECTED' && <Badge variant="danger">rejected</Badge>}
          {cand.status === 'DEFERRED' && <Badge variant="warning">deferred</Badge>}
        </p>
        <p className="figure mt-0.5 text-[10.5px] text-navy-400">
          confidence {cand.confidence != null ? `${Math.round(cand.confidence * 100)}%` : '—'}
          {' · '}{cand.extraction_method}
          {loc && <> · {loc}</>}
          {cand.match && cand.match.status !== 'PENDING' && (
            <span className="text-navy-300"> · match {cand.match.status.toLowerCase()}</span>
          )}
        </p>
        {cand.source_snippet && (
          <p className="mt-1 line-clamp-2 max-w-2xl text-[11px] italic text-navy-400">“{cand.source_snippet}”</p>
        )}
        {cand.decision_note && (
          <p className="mt-0.5 text-[11px] text-navy-300">{cand.decision_note}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {reviewed ? (
          <span className="figure text-[11px] text-navy-300">
            {cand.status === 'ACCEPTED' && cand.accepted_entity_id
              ? `entity #${cand.accepted_entity_id}`
              : 'reviewed'}
            {cand.decided_at ? ` · ${formatDateTime(cand.decided_at)}` : ''}
          </span>
        ) : (
          <>
            <Button size="sm" variant="ghost" icon={Clock}
              loading={actingId === `cand-def-${cand.id}`}
              onClick={onDefer}
            >
              Later
            </Button>
            <Button size="sm" variant="outline" icon={X}
              loading={actingId === `cand-rej-${cand.id}`}
              onClick={onReject}
            >
              Reject
            </Button>
            <Button size="sm" variant="primary" icon={Check}
              loading={actingId === `cand-${cand.id}`}
              onClick={onAccept}
            >
              Accept
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
