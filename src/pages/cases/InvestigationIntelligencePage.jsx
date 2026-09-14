/**
 * Investigation Intelligence page (stage 4).
 *
 * Seven named panels over the case's CONFIRMED data:
 * analysis status & run, contradictions, competing hypotheses,
 * evidence impact, timeline, geospatial and investigation gaps.
 *
 * The page owns the "analyzed / insufficient" flags (from the status
 * endpoint) and a reload key bumped after each analysis run; each panel
 * fetches its own data with that key so every panel shows its own
 * not-analyzed / analyzing / up-to-date / stale / insufficient / error
 * state.
 */
import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { FlaskConical } from 'lucide-react';
import { useCnaResource } from '@/hooks/useCnaResource';
import { investigationService } from '@/services/v1';
import {
  InvestigationContradictionsPanel,
  InvestigationEvidenceImpactPanel,
  InvestigationGapsPanel,
  InvestigationGeospatialPanel,
  InvestigationHypothesesPanel,
  InvestigationStatusPanel,
  InvestigationTimelinePanel,
  makeGraphHighlighter,
} from '@/components/cases/InvestigationPanels';

export function InvestigationIntelligencePage() {
  const { caseId } = useParams();
  const [analyzing, setAnalyzing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const onHighlight = makeGraphHighlighter(caseId);

  const { data: status } = useCnaResource(
    useCallback(() => investigationService.getInvestigationStatus(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );

  const analyzed = !!status?.analyzed;
  const insufficient = !!status?.insufficient;
  const stale = status?.state === 'stale';

  const onAnalyzedChange = (state) => {
    if (state === 'analyzing') setAnalyzing(true);
    else {
      setAnalyzing(false);
      setReloadKey((k) => k + 1);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-teal-600" aria-hidden />
          <p className="text-[13px] font-medium text-navy-700">
            Investigation Reasoning & Evidence Intelligence
          </p>
        </div>
        {stale && (
          <p className="text-[12px] text-amber-600">
            Confirmed data changed since the last analysis — results below are marked stale.
          </p>
        )}
      </div>

      <InvestigationStatusPanel
        caseId={caseId}
        analyzing={analyzing}
        onAnalyzedChange={onAnalyzedChange}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <InvestigationContradictionsPanel
          caseId={caseId} reloadKey={reloadKey}
          analyzed={analyzed} insufficient={insufficient}
          onHighlight={onHighlight}
        />
        <InvestigationHypothesesPanel
          caseId={caseId} reloadKey={reloadKey}
          analyzed={analyzed} insufficient={insufficient}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <InvestigationEvidenceImpactPanel
          caseId={caseId} reloadKey={reloadKey}
          analyzed={analyzed} insufficient={insufficient}
        />
        <InvestigationTimelinePanel
          caseId={caseId} reloadKey={reloadKey}
          analyzed={analyzed} insufficient={insufficient}
        />
      </div>

      <InvestigationGeospatialPanel
        caseId={caseId} reloadKey={reloadKey}
        analyzed={analyzed} insufficient={insufficient}
      />

      <InvestigationGapsPanel
        caseId={caseId} reloadKey={reloadKey}
        analyzed={analyzed} insufficient={insufficient}
        onHighlight={onHighlight}
      />
    </div>
  );
}
