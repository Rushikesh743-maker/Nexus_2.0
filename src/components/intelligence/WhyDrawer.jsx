import { Drawer } from '@/components/modals/Drawer';
import { Badge } from '@/components/ui/Badge';
import { EvidenceChain } from './EvidenceChain';

/**
 * Global "Why?" explanation drawer — NEXUS's reusable provenance surface.
 * Any analytical result can open it with a finding→record chain.
 * chain: EvidenceChain steps [{ key, label, icon, title, detail?, caption? }]
 */
export function WhyDrawer({ open, onClose, title = 'Why this result?', description, badge, chain = [] }) {
  return (
    <Drawer open={open} onClose={onClose} title={title} subtitle={badge} width={440}>
      <div className="space-y-4">
        {description && <p className="text-[13px] leading-relaxed text-navy-500">{description}</p>}
        {chain.length > 0 ? (
          <>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Provenance</p>
            <EvidenceChain chain={chain} />
          </>
        ) : (
          <Badge variant="neutral">No provenance chain recorded for this result yet.</Badge>
        )}
        <p className="rounded-lg bg-slate-50 px-3.5 py-2.5 text-[11px] leading-relaxed text-navy-400">
          Every NEXUS analytical result can explain how it was derived — from the initial finding down
          to the original record. NEXUS provides analytical assistance and investigation leads; it does
          not determine guilt or replace investigator judgment.
        </p>
      </div>
    </Drawer>
  );
}
