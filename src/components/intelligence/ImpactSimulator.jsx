import { useEffect, useMemo, useState } from 'react';
import { FlaskConical, RotateCcw, ArrowRight, ShieldCheck } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { analysisService, evidenceService, intelligenceService } from '@/services';
import { useToast } from '@/context/ToastContext';
import { cn } from '@/lib/utils';

/**
 * Evidence Impact Simulator — interactive "what if" preview.
 * The simulation NEVER mutates case data; results are clearly labelled as a
 * simulation with mock values from the analysis service.
 */
export function ImpactSimulator({ investigationId }) {
  const toast = useToast();
  const [evidence, setEvidence] = useState(null);
  const [network, setNetwork] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let active = true;
    setError(null);
    Promise.all([
      evidenceService.list(investigationId),
      intelligenceService.getNetwork(investigationId),
    ])
      .then(([ev, net]) => {
        if (!active) return;
        setEvidence(ev.items);
        setNetwork(net);
      })
      .catch((e) => active && setError(e));
    return () => {
      active = false;
    };
  }, [investigationId]);

  const previewGraph = useMemo(() => {
    // The strongest relationship chain A — B — C, by entity name. The hinge is
    // whichever end of the strongest link carries the next-strongest link on to
    // a third entity, so the chain is three distinct subjects or nothing.
    const rels = network?.relationships;
    if (!rels?.length) return null;
    const nameById = Object.fromEntries((network.entities || []).map((e) => [e.id, e.name]));
    const sorted = [...rels].sort((x, y) => y.strength - x.strength);
    const first = sorted[0];
    const next = sorted
      .slice(1)
      .find(
        (r) =>
          [r.sourceId, r.targetId].some((id) => id === first.sourceId || id === first.targetId) &&
          [r.sourceId, r.targetId].some((id) => id !== first.sourceId && id !== first.targetId)
      );
    if (!next) return null;
    const hinge = [next.sourceId, next.targetId].find((id) => id === first.sourceId || id === first.targetId);
    const tail = [next.sourceId, next.targetId].find((id) => id !== hinge);
    const head = [first.sourceId, first.targetId].find((id) => id !== hinge);
    return { a: nameById[head], b: nameById[hinge], c: nameById[tail] };
  }, [network]);

  const run = async () => {
    if (!selected) return;
    setRunning(true);
    try {
      const r = await analysisService.simulateEvidenceRemoval(investigationId, selected);
      setResult(r);
    } catch (e) {
      toast.error('Simulation failed', e.message);
    } finally {
      setRunning(false);
    }
  };

  if (error) return <ErrorState title="Could not load the simulator" description={error.message} onRetry={() => setError(null)} />;
  if (!evidence || !network) return <PageLoader label="Preparing simulator…" />;

  return (
    <Card>
      <CardHeader
        title="Evidence Impact Simulator"
        subtitle="Explore how the analysis picture would change without a record — nothing is modified."
        actions={<Badge variant="warning" dot>SIMULATION</Badge>}
      />
      <CardBody className="space-y-5">
        <div className="max-w-md">
          <Select
            label="Select evidence"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setResult(null);
            }}
            options={[
              { value: '', label: 'Choose a record…' },
              ...evidence.map((e) => ({ value: e.id, label: `${e.refNo} — ${e.title.slice(0, 42)}` })),
            ]}
            aria-label="Select evidence to simulate removing"
          />
        </div>

        {/* Current picture (schematic) */}
        {previewGraph && (
        <div className="rounded-xl border border-slate-200 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-navy-300">Current investigation</p>
          <div className="mt-3 flex items-center gap-3 font-mono text-[13px] font-semibold text-navy-700">
            <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">{previewGraph.a}</span>
            <span className="text-navy-300">───</span>
            <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">{previewGraph.b}</span>
            <span className="text-navy-300">───</span>
            <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5">{previewGraph.c}</span>
          </div>
        </div>
        )}

        {!result && (
          <Button icon={FlaskConical} onClick={run} disabled={!selected || running} loading={running}>
            Simulate Removing Evidence
          </Button>
        )}

        {/* Simulated state */}
        {result && (
          <div className="animate-fade-in space-y-4 rounded-xl border-2 border-dashed border-amber-300 bg-amber-50/50 p-4">
            <p className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.12em] text-amber-800">
              <ShieldCheck className="h-4 w-4" aria-hidden />
              Simulation — no case data changed
            </p>
            <p className="text-[13px] text-navy-600">
              Evidence <span className="font-mono font-semibold">{result.evidence?.refNo}</span> removed from simulation.
            </p>

            {result.affectedRelationship && (
              <div className="rounded-lg border border-amber-200 bg-white p-3.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">Affected relationship</p>
                <p className="mt-1 text-[13.5px] font-semibold text-navy-800">{result.affectedRelationship.label}</p>
                <p className="mt-1.5 flex items-center gap-2 font-mono text-[14px]">
                  <span className="text-navy-500">{result.affectedRelationship.before}%</span>
                  <ArrowRight className="h-4 w-4 text-navy-300" aria-hidden />
                  <span className={cn('font-bold text-amber-700')}>{result.affectedRelationship.after}%</span>
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-amber-200 bg-white p-3.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">Affected hypothesis</p>
                <p className="mt-1 text-[13.5px] font-semibold text-navy-800">
                  {result.affectedHypothesis.id} · {result.affectedHypothesis.title}
                </p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-white p-3.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-300">Leads affected</p>
                <p className="mt-1 text-[13.5px] font-semibold text-navy-800">{result.leadsAffected} investigation leads</p>
              </div>
            </div>

            <p className="text-[11px] leading-relaxed text-amber-800">
              Impact figures are mock values for demonstration. Real simulation requires the backend analysis engine.
            </p>

            <Button
              variant="outline"
              size="sm"
              icon={RotateCcw}
              onClick={() => {
                setResult(null);
                setSelected('');
              }}
            >
              Reset Simulation
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
