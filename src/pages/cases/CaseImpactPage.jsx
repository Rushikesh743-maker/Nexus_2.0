import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Waves } from 'lucide-react';
import { useCnaResource } from '@/hooks/useCnaResource';
import { investigationService } from '@/services/v1';
import { PageLoader } from '@/components/ui/LoadingState';
import { InvestigationEvidenceImpactPanel } from '@/components/cases/InvestigationPanels';
import { FreshnessBadge } from '@/components/cases/FreshnessBadge';

/**
 * Case impact — what happens analytically if a piece of evidence is
 * challenged: per-evidence linkage, impact scores and a what-if
 * simulation (the simulation is a computation over the confirmed graph,
 * clearly labelled as a simulation, never a change to the record).
 */
export function CaseImpactPage() {
  const { caseId } = useParams();
  const [reloadKey, setReloadKey] = useState(0);

  const { data: status, loading } = useCnaResource(
    useCallback(() => investigationService.getInvestigationStatus(caseId), [caseId]),
    [caseId]
  );

  if (loading && !status) return <PageLoader label="Loading impact analysis…" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Waves className="h-4 w-4 text-teal-600" aria-hidden />
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-display text-[17px] text-navy-900">Evidence impact</h2>
            <FreshnessBadge analysis={status} />
          </div>
          <p className="text-[12px] text-navy-400">
            Per-evidence analytical linkage and what-if impact over the confirmed case data.
          </p>
        </div>
      </div>
      <InvestigationEvidenceImpactPanel
        caseId={caseId}
        reloadKey={reloadKey}
        analyzed={!!status?.analyzed}
        insufficient={!!status?.insufficient}
      />
    </div>
  );
}
