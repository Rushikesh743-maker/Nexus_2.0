import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { MoveVertical, Eye } from 'lucide-react';
import { Modal } from '@/components/modals/Modal';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Avatar } from '@/components/ui/Avatar';
import { ConfidenceMeter } from './ConfidenceMeter';
import { EvidenceChain, buildChain } from './EvidenceChain';
import { RELATIONSHIP_TYPES } from '@/lib/constants';
import { hashString, truncate } from '@/lib/utils';

/**
 * "Why this connection?" panel — presents how a relationship is supported:
 * both endpoints, analyst confidence, supporting vs contradicting evidence
 * reference lists, and an interactive evidence chain down to the original
 * record.
 *
 * Presentation only: evidence references are derived deterministically from
 * the case evidence list (mock values). No contradiction or inference logic
 * runs in the client — backend analysis services will own these numbers.
 */
export function RelationshipWhyModal({ open, onClose, relationship, entitiesById = {}, evidence = [], investigationId }) {
  const navigate = useNavigate();

  const { source, target, typeMeta, supportingRefs, contradictingRefs, linkedEvidence, chain } = useMemo(() => {
    if (!relationship) return {};
    const src = entitiesById[relationship.sourceId];
    const tgt = entitiesById[relationship.targetId];
    const meta = RELATIONSHIP_TYPES[relationship.type] || RELATIONSHIP_TYPES.associate;

    // Deterministic mock evidence attribution (placeholder until backend).
    const h = hashString(relationship.id || `${relationship.sourceId}-${relationship.targetId}`);
    const supportCount = Math.max(1, Math.min(3, Math.round((relationship.strength || 50) / 30)));
    const used = new Set();
    const support = [];
    for (let i = 0; i < supportCount && evidence.length; i += 1) {
      const idx = (h + i * 7) % evidence.length;
      if (used.has(idx)) continue;
      used.add(idx);
      support.push(evidence[idx]);
    }
    const contradict =
      relationship.strength >= 75 || evidence.length < 2 ? [] : [evidence[(h + 11) % evidence.length]];

    return {
      source: src,
      target: tgt,
      typeMeta: meta,
      supportingRefs: support,
      contradictingRefs: contradict,
      linkedEvidence: support[0] || null,
      chain: buildChain({ source: src, target: tgt, relationship, evidence: support[0] || null }),
    };
  }, [relationship, entitiesById, evidence]);

  if (!relationship) return null;

  const viewEvidence = (record) => {
    onClose();
    navigate(`/investigations/${investigationId}/evidence${record ? `?evidence=${record.id}` : ''}`);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="md"
      title="Why this connection?"
      description="How this relationship is supported — presentation of recorded data, no automated judgement."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button icon={Eye} onClick={() => viewEvidence(linkedEvidence)}>
            View Evidence
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {/* Endpoints */}
        <div className="rounded-xl border border-slate-200 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Relationship</p>
          <p className="mt-1 text-[13px] font-medium text-navy-600">
            {source?.name || 'Entity A'} ↔ {target?.name || 'Entity B'}
          </p>
          <div className="mt-3 flex flex-col items-center gap-2">
            <EndpointRow entity={source} />
            <span className="flex flex-col items-center text-navy-300">
              <MoveVertical className="h-5 w-5" aria-hidden />
              <span className="-mt-0.5 rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy-500">
                {relationship.label || typeMeta.label}
              </span>
            </span>
            <EndpointRow entity={target} />
          </div>
        </div>

        {/* Confidence + evidence lists */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Confidence</p>
            <div className="mt-2.5">
              <ConfidenceMeter value={relationship.strength} label="Analyst confidence" />
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Evidence</p>
            <div className="mt-2.5 space-y-2">
              <div>
                <p className="text-[11px] font-medium text-emerald-700">Supporting evidence ({supportingRefs.length})</p>
                <ul className="mt-1 space-y-1">
                  {supportingRefs.map((record) => (
                    <li key={record.id}>
                      <button
                        type="button"
                        onClick={() => viewEvidence(record)}
                        className="flex w-full items-center gap-1.5 rounded border border-slate-100 px-1.5 py-1 text-left text-[11.5px] text-navy-600 transition-colors hover:border-teal-300 hover:bg-teal-50/40"
                      >
                        <span className="rounded bg-navy-50 px-1 font-mono text-[10px] font-semibold text-navy-500">{record.refNo}</span>
                        <span className="truncate">{truncate(record.title, 26)}</span>
                      </button>
                    </li>
                  ))}
                  {supportingRefs.length === 0 && <li className="text-[11.5px] text-navy-300">No case evidence available (mock).</li>}
                </ul>
              </div>
              <div>
                <p className="text-[11px] font-medium text-amber-700">Contradicting evidence ({contradictingRefs.length})</p>
                <ul className="mt-1 space-y-1">
                  {contradictingRefs.map((record) => (
                    <li key={record.id}>
                      <button
                        type="button"
                        onClick={() => viewEvidence(record)}
                        className="flex w-full items-center gap-1.5 rounded border border-slate-100 px-1.5 py-1 text-left text-[11.5px] text-navy-600 transition-colors hover:border-amber-300 hover:bg-amber-50/40"
                      >
                        <span className="rounded bg-amber-50 px-1 font-mono text-[10px] font-semibold text-amber-700">{record.refNo}</span>
                        <span className="truncate">{truncate(record.title, 26)}</span>
                      </button>
                    </li>
                  ))}
                  {contradictingRefs.length === 0 && <li className="text-[11.5px] text-navy-300">None recorded.</li>}
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Evidence chain */}
        <div>
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">
            From finding to original record
          </p>
          <EvidenceChain chain={chain} />
        </div>

        <p className="rounded-lg bg-slate-50 px-3.5 py-2.5 text-[11px] leading-relaxed text-navy-400">
          Evidence references are mock presentation values. Contradiction checking and confidence scoring will be performed by
          backend analysis services — nothing is inferred in the browser.
        </p>
      </div>
    </Modal>
  );
}

function EndpointRow({ entity }) {
  const typeMetaLabel = entity ? entity.role || 'Entity' : 'Unknown entity';
  return (
    <div className="flex w-full items-center gap-3 rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2">
      <Avatar name={entity?.name || '?'} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold text-navy-800">{entity?.name || 'Unknown entity'}</p>
        <p className="text-[11px] text-navy-400">{typeMetaLabel}</p>
      </div>
    </div>
  );
}
