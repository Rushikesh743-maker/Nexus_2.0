/**
 * Investigation Intelligence panels (stage 4) — seven named panels:
 *
 *  1. Analysis status & run   (not-analyzed / analyzing / up-to-date /
 *                              stale / insufficient / error states)
 *  2. Contradictions          potential contradictions, confirmed records
 *  3. Competing hypotheses    transparent deterministic scores
 *  4. Evidence impact         per-evidence linkage + in-memory simulation
 *  5. Timeline intelligence   overlaps, proximity, sequence, gaps
 *  6. Geospatial intelligence co-location, proximity, sequence + map
 *  7. Investigation gaps      evidence / relationship / identity coverage
 *
 * Every panel is analytical over CONFIRMED data; nothing is proof.
 * "Show in graph" reuses the case graph's temporary highlight.
 *
 * Structure follows the stage-3 convention: *Panel = data fetching +
 * state; *Body = pure presentation (independently testable in the
 * frontend sanity harness).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, AlertTriangle, GitBranch, ListChecks, MapPin, Scale,
  ShieldAlert, Trash2, UserCheck,
} from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Spinner } from '@/components/ui/LoadingState';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { investigationService } from '@/services/v1';
import { FindingRow } from '@/components/cases/GraphFindingsPanel';

// ------------------------------------------------------------------- meta
export const INVESTIGATION_STATE_META = {
  'not-analyzed': { label: 'Not analyzed', variant: 'neutral' },
  analyzing: { label: 'Analyzing…', variant: 'info' },
  'up-to-date': { label: 'Up to date', variant: 'success' },
  stale: { label: 'Stale — data changed', variant: 'warning' },
  insufficient: { label: 'Insufficient confirmed data', variant: 'danger' },
  error: { label: 'Error', variant: 'danger' },
};

export const CONTRADICTION_TYPE_META = {
  TIMELINE_CONTRADICTION: { label: 'Timeline', variant: 'danger' },
  LOCATION_CONTRADICTION: { label: 'Location', variant: 'danger' },
  RELATIONSHIP_CONTRADICTION: { label: 'Relationship', variant: 'warning' },
  EVIDENCE_CONTRADICTION: { label: 'Evidence', variant: 'warning' },
};

export const TIMELINE_TYPE_META = {
  EVENT_OVERLAP: { label: 'Overlap', variant: 'info' },
  TEMPORAL_PROXIMITY: { label: 'Proximity', variant: 'teal' },
  EVENT_SEQUENCE: { label: 'Sequence', variant: 'neutral' },
  TIMELINE_GAP: { label: 'Potential gap', variant: 'warning' },
};

export const GEO_TYPE_META = {
  CO_LOCATION: { label: 'Co-location', variant: 'teal' },
  LOCATION_PROXIMITY: { label: 'Proximity', variant: 'info' },
  LOCATION_SEQUENCE: { label: 'Sequence', variant: 'neutral' },
};

export const GAP_TYPE_META = {
  EVIDENCE_GAP: { label: 'Evidence gap', variant: 'warning' },
  RELATIONSHIP_GAP: { label: 'Relationship gap', variant: 'info' },
  TIMELINE_GAP: { label: 'Timeline gap', variant: 'neutral' },
  IDENTITY_GAP: { label: 'Identity gap', variant: 'danger' },
};

export const CONFIDENCE_BAND_META = {
  HIGH: { variant: 'success', label: 'HIGH' },
  MEDIUM: { variant: 'warning', label: 'MEDIUM' },
  LOW: { variant: 'neutral', label: 'LOW' },
};

export function bandMeta(band) {
  return CONFIDENCE_BAND_META[band] || { variant: 'neutral', label: band };
}

export function ScoreBar({ score }) {
  const pct = Math.round((score || 0) * 100);
  const meta = bandMeta(score >= 0.67 ? 'HIGH' : score >= 0.34 ? 'MEDIUM' : 'LOW');
  const color =
    meta.variant === 'success' ? 'bg-emerald-500'
    : meta.variant === 'warning' ? 'bg-amber-500'
    : 'bg-slate-400';
  return (
    <div className="flex items-center gap-2" aria-label={`analytical score ${score}`}>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[11.5px] text-navy-600">{(score || 0).toFixed(2)}</span>
    </div>
  );
}

/**
 * Shared body states: loading / error / empty (no data) / data.
 * `empty` is the not-analyzed|insufficient|no-results node; `children`
 * is the data branch (list + optional simulation area).
 */
export function PanelBody({ loading, data, error, onRetry, empty, children }) {
  if (loading && !data) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-navy-400">
        <Spinner className="h-4 w-4" /> Loading…
      </div>
    );
  }
  if (error && !data) {
    return <ErrorState title="Could not load analysis" description={error.message} onRetry={onRetry} compact />;
  }
  if (!data) return empty;
  return children;
}

// ================================================== 1. status & run panel
/** Pure presentation of the analysis-status body (all six states). */
export function StatusBody({ loading, error, data, analyzing, onRun }) {
  const state = loading ? 'analyzing'
    : error ? 'error'
    : data?.state || 'not-analyzed';
  const meta = INVESTIGATION_STATE_META[state] || INVESTIGATION_STATE_META['not-analyzed'];

  return (
    <div className="space-y-2 px-4 py-3">
      <p className="text-[12.5px] leading-relaxed text-navy-500">
        {error && !data ? error.message : (data?.reason || 'Checking analysis state…')}
      </p>
      {data && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-navy-400">
          <span>{data.current_findings} current finding(s)</span>
          <span>{data.stale_findings} stale</span>
          <span>{data.hypotheses} hypothesis(es)</span>
          <span>{data.timeline?.events_with_timestamp}/{data.timeline?.events_total} dated events</span>
          <span>{data.geospatial?.locations_with_coords}/{data.geospatial?.locations_total} locations with coordinates</span>
        </div>
      )}
      <div className="flex items-center gap-2 pt-1">
        <Badge variant={meta.variant} dot>{meta.label}</Badge>
        <Button size="sm" icon={Activity} loading={analyzing || state === 'analyzing'} onClick={onRun}>
          {(analyzing || state === 'analyzing') ? 'Analyzing…' : 'Run Analysis'}
        </Button>
      </div>
      <p className="rounded-md bg-slate-50 px-3 py-2 text-[11.5px] leading-relaxed text-navy-400">
        Analytical support only — results are potential leads for investigator review,
        never proof, and never a probability of guilt.
      </p>
    </div>
  );
}

export function InvestigationStatusPanel({ caseId, analyzing, onAnalyzedChange }) {
  const toast = useToast();
  const [reloadKey, setReloadKey] = useState(0);
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.getInvestigationStatus(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );

  const runAnalysis = async () => {
    onAnalyzedChange?.('analyzing');
    try {
      const res = await investigationService.analyzeInvestigation(caseId);
      toast.success(
        res.recomputed
          ? `Investigation analysis complete — ${res.findings.length} finding(s).`
          : 'Confirmed data unchanged — showing the existing analysis.'
      );
      onAnalyzedChange?.('up-to-date');
      setReloadKey((k) => k + 1);
    } catch (err) {
      if (err.code === 'INSUFFICIENT_CONFIRMED_DATA') {
        toast.warning('Insufficient confirmed data to analyze this case yet.');
        onAnalyzedChange?.('insufficient');
      } else {
        toast.error(err.message || 'Investigation analysis failed.');
        onAnalyzedChange?.('error');
      }
      setReloadKey((k) => k + 1);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Investigation Analysis"
        subtitle={data ? `Snapshot ${data.graph_version}` : 'Reasoning & evidence intelligence over confirmed data'}
      />
      <StatusBody
        loading={loading} error={error} data={data}
        analyzing={analyzing} onRun={runAnalysis}
      />
    </Card>
  );
}

// ============================================ 2. contradictions panel
export function ContradictionsBody({ loading, data, error, onRetry, analyzed, insufficient, onHighlight, onToast, onChanged }) {
  const empty = (
    <EmptyState
      icon={insufficient ? ShieldAlert : Scale}
      title={insufficient ? 'Insufficient confirmed data'
        : analyzed ? 'No potential contradictions detected'
        : 'Not analyzed yet'}
      description={insufficient
        ? 'This case has no confirmed graph data to analyze. Record confirmed entities and relationships first — the engine never guesses.'
        : analyzed
        ? 'The confirmed records contain no detected inconsistencies above the documented rules. This is a statement about the current confirmed data, not about the case.'
        : 'Run the investigation analysis to detect potential contradictions among the confirmed records.'}
      compact />
  );
  return (
    <PanelBody loading={loading} data={data} error={error} onRetry={onRetry} empty={empty}>
      {data && data.current_findings.length > 0 && (
        <ul className="max-h-[380px] divide-y divide-line-soft overflow-y-auto">
          {data.current_findings.map((f) => (
            <FindingRow key={f.id} finding={f}
              onHighlight={onHighlight}
              onToast={onToast}
              onChanged={onChanged}
              reviewFn={investigationService.reviewInvestigationFinding}
              dismissFn={investigationService.dismissInvestigationFinding} />
          ))}
        </ul>
      )}
      {data && data.current_findings.length === 0 && (
        <EmptyState icon={Scale} title="No potential contradictions detected"
          description="The confirmed records contain no detected inconsistencies above the documented rules. This is a statement about the current confirmed data, not about the case." compact />
      )}
      {data && data.stale_findings.length > 0 && (
        <details className="border-t border-line-soft px-4 py-2.5">
          <summary className="cursor-pointer text-[12px] font-medium text-navy-500">
            Earlier snapshots ({data.stale_findings.length}) — confirmed data changed since
          </summary>
          <ul className="mt-2 space-y-1.5">
            {data.stale_findings.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-1.5 text-[12px] text-navy-400">
                <Badge variant="neutral">{f.title}</Badge>
                <span className="font-mono text-[10.5px]">{f.graph_version}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </PanelBody>
  );
}

export function InvestigationContradictionsPanel({ caseId, reloadKey, analyzed, insufficient, onHighlight }) {
  const toast = useToast();
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.listContradictions(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );
  return (
    <Card>
      <CardHeader title="Potential Contradictions"
        subtitle="Confirmed records that may be inconsistent — for review, never resolved automatically" />
      <ContradictionsBody
        loading={loading} data={data} error={error} onRetry={reload}
        analyzed={analyzed} insufficient={insufficient}
        onHighlight={onHighlight}
        onToast={(m, k) => toast[k]?.(m)}
        onChanged={reload}
      />
    </Card>
  );
}

// ============================================ 3. hypotheses panel
export function HypothesisItem({ h, onAct }) {
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={h.hypothesis_type === 'INVESTIGATOR' ? 'violet' : 'info'}>
          {h.hypothesis_type === 'INVESTIGATOR' ? 'Investigator'
            : h.hypothesis_type === 'GENERATED_CONTRADICTION' ? 'Contradiction' : 'Structure'}
        </Badge>
        <Badge variant={bandMeta(h.confidence_band).variant}>{h.confidence_band} support</Badge>
        {h.stale && <Badge variant="warning">Stale — data changed</Badge>}
        {h.status !== 'ACTIVE' && (
          <Badge variant={h.status === 'REVIEWED' ? 'success' : 'danger'}>
            {h.status === 'REVIEWED' ? 'Reviewed' : 'Dismissed'}
          </Badge>
        )}
      </div>
      <p className="mt-1.5 text-[13px] font-medium leading-snug text-navy-800">{h.title}</p>
      {h.description && <p className="mt-0.5 text-[12px] leading-relaxed text-navy-500">{h.description}</p>}
      <div className="mt-1.5"><ScoreBar score={h.analytical_score} /></div>
      <details className="mt-1.5">
        <summary className="cursor-pointer text-[11.5px] font-medium text-navy-500">
          Score components & signals
        </summary>
        <div className="mt-1.5 space-y-1">
          {(h.explanation || []).map((line, i) => (
            <p key={i} className="text-[11.5px] leading-relaxed text-navy-500">{line}</p>
          ))}
          <p className="font-mono text-[10.5px] text-navy-400">{h.analysis_method}</p>
          {h.review_note && (
            <p className="text-[11.5px] italic text-navy-400">
              Review note ({h.reviewed_by_name || '—'}): {h.review_note}
            </p>
          )}
        </div>
      </details>
      {h.status === 'ACTIVE' && (
        <div className="mt-2 flex gap-1.5">
          <Button variant="ghost" size="sm" icon={UserCheck} onClick={() => onAct?.(h, 'reviewed')}>Review</Button>
          <Button variant="ghost" size="sm" icon={Trash2} onClick={() => onAct?.(h, 'dismissed')}>Dismiss</Button>
        </div>
      )}
    </li>
  );
}

export function HypothesesBody({ loading, data, error, onRetry, analyzed, insufficient, onAct, showForm, formNode }) {
  const empty = (
    <EmptyState icon={GitBranch}
      title={insufficient ? 'Insufficient confirmed data'
        : analyzed ? 'No hypotheses yet'
        : 'Not analyzed yet'}
      description={insufficient
        ? 'This case has no confirmed graph data. The hypothesis engine only works on confirmed records.'
        : analyzed
        ? 'The analysis ran and produced no competing hypotheses (no contradictions or indirect person pairs above the documented thresholds). You can still record your own below.'
        : 'Run the investigation analysis to generate competing explanations of the confirmed data.'}
      compact />
  );
  return (
    <PanelBody loading={loading} data={data} error={error} onRetry={onRetry} empty={empty}>
      {data && data.hypotheses.length === 0 && (
        <EmptyState icon={GitBranch} title="No hypotheses yet"
          description="The analysis ran and produced no competing hypotheses (no contradictions or indirect person pairs above the documented thresholds). You can still record your own below." compact />
      )}
      {data && data.hypotheses.length > 0 && (
        <ul className="max-h-[420px] divide-y divide-line-soft overflow-y-auto">
          {data.hypotheses.map((h) => (
            <HypothesisItem key={h.id} h={h} onAct={onAct} />
          ))}
        </ul>
      )}
      {showForm && formNode}
    </PanelBody>
  );
}

function HypothesisForm({ caseId, onDone }) {
  const toast = useToast();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!title.trim()) { toast.error('A title is required.'); return; }
    setBusy(true);
    try {
      await investigationService.createHypothesis(caseId, {
        title: title.trim(), description: description.trim() || null,
      });
      toast.success('Hypothesis recorded and scored.');
      onDone();
    } catch (err) {
      toast.error(err.message || 'Could not create the hypothesis.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 border-t border-line-soft px-4 py-3">
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255}
        placeholder="Hypothesis title (required)"
        className="w-full rounded-md border border-line-soft bg-white px-3 py-1.5 text-[12.5px] outline-none focus:border-teal-500" />
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000}
        placeholder="Description (optional)" rows={2}
        className="w-full rounded-md border border-line-soft bg-white px-3 py-1.5 text-[12.5px] outline-none focus:border-teal-500" />
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-navy-400">
          Scored with the same documented formula as generated hypotheses.
        </p>
        <Button size="sm" loading={busy} onClick={submit}>Record hypothesis</Button>
      </div>
    </div>
  );
}

export function InvestigationHypothesesPanel({ caseId, reloadKey, analyzed, insufficient }) {
  const toast = useToast();
  const [reloadInner, setReloadInner] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.listHypotheses(caseId), [caseId, reloadKey, reloadInner]),
    [caseId, reloadKey, reloadInner]
  );
  const refresh = () => setReloadInner((k) => k + 1);

  const act = async (h, action) => {
    try {
      if (action === 'reviewed') await investigationService.reviewHypothesis(caseId, h.id);
      else await investigationService.dismissHypothesis(caseId, h.id);
      toast.success(action === 'reviewed'
        ? 'Hypothesis marked as reviewed.'
        : 'Hypothesis dismissed (kept in audit history).');
      refresh();
    } catch (err) {
      toast.error(err.message || 'Hypothesis review failed.');
    }
  };

  return (
    <Card>
      <CardHeader title="Competing Hypotheses"
        subtitle="Transparent deterministic scores — analytical support, not probability of guilt"
        actions={<Button variant="ghost" size="sm" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Close form' : 'New hypothesis'}
        </Button>} />
      <HypothesesBody
        loading={loading} data={data} error={error} onRetry={reload}
        analyzed={analyzed} insufficient={insufficient}
        onAct={act} showForm={showForm}
        formNode={showForm ? <HypothesisForm caseId={caseId} onDone={() => { setShowForm(false); refresh(); }} /> : null}
      />
    </Card>
  );
}

// ============================================ 4. evidence impact panel
export function EvidenceImpactBody({ loading, data, error, onRetry, analyzed, insufficient, simulation, onSimulate, simBusy }) {
  const empty = (
    <EmptyState icon={ListChecks}
      title={insufficient ? 'Insufficient confirmed data'
        : analyzed ? 'No evidence records in this case'
        : 'Not analyzed yet'}
      description={insufficient
        ? 'This case has no confirmed data. Evidence impact is computed only from confirmed records and their linkage.'
        : analyzed
        ? 'This case has no evidence records linked into the confirmed analysis.'
        : 'Run the investigation analysis (or wait for it) to compute per-evidence impact.'}
      compact />
  );
  const dist = data?.distribution;
  return (
    <PanelBody loading={loading} data={data} error={error} onRetry={onRetry} empty={empty}>
      {data && data.evidence_impacts.length === 0 && (
        <EmptyState icon={ListChecks} title="No evidence records in this case"
          description="This case has no evidence records linked into the confirmed analysis." compact />
      )}
      {data && data.evidence_impacts.length > 0 && (
        <>
          <div className="flex gap-1.5 border-b border-line-soft px-4 py-2">
            <Badge variant="success">{dist.HIGH} high</Badge>
            <Badge variant="warning">{dist.MEDIUM} medium</Badge>
            <Badge variant="neutral">{dist.LOW} low</Badge>
          </div>
          <ul className="max-h-[380px] divide-y divide-line-soft overflow-y-auto">
            {data.evidence_impacts.map((e) => (
              <li key={e.evidence_id} className="px-4 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[12.5px] font-medium text-navy-800">Evidence #{e.evidence_id}</span>
                    <Badge variant={e.impact_band === 'HIGH' ? 'success' : e.impact_band === 'MEDIUM' ? 'warning' : 'neutral'}>
                      {e.impact_band}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <ScoreBar score={e.impact_score} />
                    <Button variant="ghost" size="sm"
                      loading={simBusy === e.evidence_id}
                      onClick={() => onSimulate?.(e.evidence_id)}>
                      Simulate removal
                    </Button>
                  </div>
                </div>
                <p className="mt-1 text-[11.5px] text-navy-500">{e.impact_role}</p>
              </li>
            ))}
          </ul>
        </>
      )}
      {simulation && (
        <div className="space-y-2 border-t border-line-soft bg-slate-50/60 px-4 py-3">
          <p className="text-[12.5px] font-medium text-navy-800">
            What-if: evidence #{simulation.evidence_id} removed
          </p>
          <p className="rounded-md bg-amber-50 px-3 py-1.5 text-[11.5px] text-amber-700">
            Simulation only — stored evidence is not modified.
          </p>
          <div className="grid gap-2 text-[11.5px] text-navy-600 sm:grid-cols-2">
            <div className="rounded-md bg-white px-3 py-2">
              <p className="font-medium text-navy-800">Graph diff</p>
              <p>Components: {simulation.diff.components_before} → {simulation.diff.components_after}</p>
              <p>Largest component: {simulation.diff.largest_component_before} → {simulation.diff.largest_component_after}</p>
              <p>Edges removed: {simulation.edges_removed.length}</p>
              <p>Newly isolated entities: {simulation.newly_isolated_entities.length
                ? simulation.newly_isolated_entities.map((n) => n.name || n.node).join(', ')
                : 'none'}</p>
            </div>
            <div className="rounded-md bg-white px-3 py-2">
              <p className="font-medium text-navy-800">Signal</p>
              <p>Degree changes: {simulation.diff.degree_changes.length}</p>
              <p>Betweenness changes: {simulation.diff.betweenness_changes.length}</p>
              <p>Newly disconnected pairs: {simulation.diff.newly_disconnected_pairs.length}</p>
              <p>Affected findings: {simulation.affected_findings.length
                ? simulation.affected_findings.map((id) => `#${id}`).join(', ')
                : 'none'}</p>
            </div>
          </div>
        </div>
      )}
    </PanelBody>
  );
}

export function InvestigationEvidenceImpactPanel({ caseId, reloadKey, analyzed, insufficient }) {
  const toast = useToast();
  const [simulation, setSimulation] = useState(null);
  const [simBusy, setSimBusy] = useState(null);
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.getEvidenceImpact(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );

  const simulate = async (evidenceId) => {
    setSimBusy(evidenceId);
    try {
      const res = await investigationService.simulateEvidenceImpact(caseId, evidenceId);
      setSimulation(res);
    } catch (err) {
      toast.error(err.message || 'Simulation failed.');
    } finally {
      setSimBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader title="Evidence Impact"
        subtitle="Structural linkage of each evidence record — not credibility or authenticity" />
      <EvidenceImpactBody
        loading={loading} data={data} error={error} onRetry={reload}
        analyzed={analyzed} insufficient={insufficient}
        simulation={simulation} onSimulate={simulate} simBusy={simBusy}
      />
    </Card>
  );
}

// ============================================ 5. timeline panel
export function TimelineBody({ loading, data, error, onRetry, analyzed, insufficient }) {
  const empty = (
    <EmptyState icon={ListChecks}
      title={insufficient ? 'Insufficient confirmed data'
        : analyzed
        ? (data && data.insufficient ? 'Insufficient timeline data' : 'No timeline patterns detected')
        : 'Not analyzed yet'}
      description={insufficient
        ? 'This case has no confirmed data.'
        : analyzed
        ? (data && data.insufficient
          ? 'Fewer than two dated confirmed events — the timeline engine cannot report patterns without timestamps. Undated events are counted, never guessed at.'
          : 'The confirmed events contain no overlaps, proximities, sequences or gaps above the documented thresholds.')
        : 'Run the investigation analysis to compute timeline patterns over the confirmed events.'}
      compact />
  );
  return (
    <PanelBody loading={loading} data={data} error={error} onRetry={onRetry} empty={empty}>
      {data && data.results.length === 0 && (
        <EmptyState icon={ListChecks} title="No timeline patterns detected"
          description={data.insufficient
            ? 'Fewer than two dated confirmed events — the timeline engine cannot report patterns without timestamps. Undated events are counted, never guessed at.'
            : 'The confirmed events contain no overlaps, proximities, sequences or gaps above the documented thresholds.'} compact />
      )}
      {data && data.results.length > 0 && (
        <ul className="max-h-[380px] divide-y divide-line-soft overflow-y-auto">
          {data.results.map((r, i) => {
            const meta = TIMELINE_TYPE_META[r.timeline_type] || { label: r.timeline_type, variant: 'neutral' };
            return (
              <li key={`${r.timeline_type}-${i}`} className="px-4 py-2.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant={meta.variant}>{meta.label}</Badge>
                  {r.interval_minutes != null && (
                    <span className="font-mono text-[11px] text-navy-400">
                      {r.timeline_type === 'TIMELINE_GAP'
                        ? `gap ${(r.interval_minutes / 60).toFixed(1)} h`
                        : `${r.interval_minutes} min`}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[12.5px] font-medium leading-snug text-navy-800">{r.title}</p>
                <p className="mt-0.5 text-[11.5px] leading-relaxed text-navy-500">{r.summary}</p>
                <details className="mt-1">
                  <summary className="cursor-pointer text-[11px] font-medium text-navy-500">Details</summary>
                  <ul className="mt-1 space-y-0.5">
                    {(r.explanation || []).map((line, j) => (
                      <li key={j} className="text-[11.5px] leading-relaxed text-navy-500">{line}</li>
                    ))}
                  </ul>
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </PanelBody>
  );
}

export function InvestigationTimelinePanel({ caseId, reloadKey, analyzed, insufficient }) {
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.getTimelineAnalysis(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );
  return (
    <Card>
      <CardHeader title="Timeline Intelligence"
        subtitle={data
          ? `${data.events_with_timestamp}/${data.events_total} dated events · ${data.events_without_timestamp} without timestamps`
          : 'Overlaps, proximity, sequence and potential gaps over confirmed events'} />
      <TimelineBody loading={loading} data={data} error={error} onRetry={reload}
        analyzed={analyzed} insufficient={insufficient} />
    </Card>
  );
}

// ============================================ 6. geospatial panel
export function GeospatialBody({ loading, data, error, onRetry, analyzed, insufficient }) {
  const [MapComp, setMapComp] = useState(null);
  useEffect(() => {
    let alive = true;
    if (data && data.observations.length > 0) {
      import('@/components/map/InvestigationMap').then((m) => {
        if (alive) setMapComp(() => m.InvestigationMap);
      }).catch(() => { /* offline map degrades to list-only */ });
    }
    return () => { alive = false; };
  }, [data]);

  const mapLocations = useMemo(() => {
    if (!data) return [];
    const byId = new Map();
    data.observations.forEach((o) => {
      const prev = byId.get(o.location_id);
      byId.set(o.location_id, {
        id: o.location_id, lat: o.latitude, lng: o.longitude, name: o.location_name,
        type: 'location',
        eventsCount: (prev ? prev.eventsCount : 0) + 1,
      });
    });
    return [...byId.values()];
  }, [data]);

  const empty = (
    <EmptyState icon={MapPin}
      title={insufficient ? 'Insufficient confirmed data'
        : data && data.location_data_insufficient ? 'LOCATION_DATA_INSUFFICIENT'
        : analyzed ? 'No geospatial patterns detected'
        : 'Not analyzed yet'}
      description={insufficient
        ? 'This case has no confirmed data.'
        : data && data.location_data_insufficient
        ? 'No confirmed location observations with coordinates exist for this case. The engine never fabricates coordinates — record confirmed locations first.'
        : analyzed
        ? 'The confirmed location data produced no co-location, proximity or multi-location sequence above the documented thresholds.'
        : 'Run the investigation analysis to compute geospatial patterns over the confirmed locations.'}
      compact />
  );

  return (
    <PanelBody loading={loading} data={data} error={error} onRetry={onRetry} empty={empty}>
      {data && data.results.length === 0 && (
        <EmptyState icon={MapPin} title="No geospatial patterns detected"
          description="The confirmed location data produced no co-location, proximity or multi-location sequence above the documented thresholds." compact />
      )}
      {data && data.results.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ul className="max-h-[380px] divide-y divide-line-soft overflow-y-auto">
            {data.results.map((r, i) => {
              const meta = GEO_TYPE_META[r.geo_type] || { label: r.geo_type, variant: 'neutral' };
              return (
                <li key={`${r.geo_type}-${i}`} className="px-4 py-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant={meta.variant}>{meta.label}</Badge>
                    {r.distance_km != null && (
                      <span className="font-mono text-[11px] text-navy-400">{r.distance_km} km</span>
                    )}
                    {r.time_difference_minutes != null && (
                      <span className="font-mono text-[11px] text-navy-400">Δ {r.time_difference_minutes} min</span>
                    )}
                  </div>
                  <p className="mt-1 text-[12.5px] font-medium leading-snug text-navy-800">{r.title}</p>
                  <p className="mt-0.5 text-[11.5px] leading-relaxed text-navy-500">{r.summary}</p>
                </li>
              );
            })}
          </ul>
          <div className="min-h-[280px]">
            {MapComp ? (
              <MapComp locations={mapLocations} movementLegs={[]} className="h-[360px]" />
            ) : (
              <div className="flex h-full items-center justify-center rounded-md border border-line-soft bg-slate-50 text-[12px] text-navy-400">
                Map unavailable — observations listed on the left.
              </div>
            )}
          </div>
        </div>
      )}
    </PanelBody>
  );
}

export function InvestigationGeospatialPanel({ caseId, reloadKey, analyzed, insufficient }) {
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.getGeospatialAnalysis(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );
  return (
    <Card>
      <CardHeader title="Geospatial Intelligence"
        subtitle={data
          ? `${data.observations_count} confirmed location observation(s)`
          : 'Co-location, proximity and recorded location sequences — haversine, no GIS services'} />
      <GeospatialBody loading={loading} data={data} error={error} onRetry={reload}
        analyzed={analyzed} insufficient={insufficient} />
    </Card>
  );
}

// ============================================ 7. gaps panel
export function GapsBody({ loading, data, error, onRetry, analyzed, insufficient, onHighlight, onToast, onChanged }) {
  const empty = (
    <EmptyState icon={AlertTriangle}
      title={insufficient ? 'Insufficient confirmed data'
        : analyzed ? 'No investigation gaps detected'
        : 'Not analyzed yet'}
      description={insufficient
        ? 'This case has no confirmed data.'
        : analyzed
        ? 'The confirmed record shows no coverage gaps above the documented rules (evidence, relationship, timeline or identity).'
        : 'Run the investigation analysis to detect where the confirmed record has no coverage.'}
      compact />
  );
  return (
    <PanelBody loading={loading} data={data} error={error} onRetry={onRetry} empty={empty}>
      {data && data.current_findings.length > 0 && (
        <ul className="max-h-[380px] divide-y divide-line-soft overflow-y-auto">
          {data.current_findings.map((f) => (
            <FindingRow key={f.id} finding={f}
              onHighlight={onHighlight}
              onToast={onToast}
              onChanged={onChanged}
              reviewFn={investigationService.reviewInvestigationFinding}
              dismissFn={investigationService.dismissInvestigationFinding} />
          ))}
        </ul>
      )}
    </PanelBody>
  );
}

export function InvestigationGapsPanel({ caseId, reloadKey, analyzed, insufficient, onHighlight }) {
  const toast = useToast();
  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => investigationService.listInvestigationGaps(caseId), [caseId, reloadKey]),
    [caseId, reloadKey]
  );
  return (
    <Card>
      <CardHeader title="Investigation Gaps"
        subtitle="Where the confirmed record has no coverage — potential investigation gaps, never implications" />
      <GapsBody
        loading={loading} data={data} error={error} onRetry={reload}
        analyzed={analyzed} insufficient={insufficient}
        onHighlight={onHighlight}
        onToast={(m, k) => toast[k]?.(m)}
        onChanged={reload}
      />
    </Card>
  );
}

/** "Show in graph" — reuses the case graph's temporary highlight. */
export function makeGraphHighlighter(caseId) {
  const navigate = useNavigate();
  return (entityIds, label) => {
    if (!entityIds?.length) return;
    navigate(`/cases/${caseId}/graph?highlight=${entityIds.join(',')}&label=${encodeURIComponent(label)}`);
  };
}
