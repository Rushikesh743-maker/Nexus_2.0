import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, ChevronRight, ChevronLeft, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { investigationService } from '@/services';
import { storage } from '@/lib/storage';

const KEY = 'nexus.demoTour';
export const DEMO_TOUR_EVENT = 'nexus:demo-tour';

/**
 * SIH 3-minute demo mode — a guided walkthrough that drives the SAME app
 * through its screens (no separate fake site). Start from the topbar
 * "Demo Mode" button or localStorage flag.
 */
const STEPS = [
  { label: 'Dashboard', path: '/dashboard', hint: 'Caseload overview — stats, recent investigations, activity and quick actions.' },
  { label: 'Investigation', path: '/investigations', hint: 'Open a case file — table or card view with filters.' },
  { label: 'Upload Evidence', path: '/investigations/:id/evidence?log=1', hint: 'Drag-and-drop upload with processing lifecycle. Try “Add demo files”.' },
  { label: 'Entity Extraction', path: '/investigations/:id/network', hint: 'Processed evidence yields entities — each with resolution status for analyst review.' },
  { label: 'Network', path: '/investigations/:id/network', hint: 'Link graph: search, filter, expand connections, highlight analysis, “Why this connection?”.' },
  { label: 'Map', path: '/investigations/:id/map', hint: 'Location intelligence with movement traces — all coordinates from case data.' },
  { label: 'Timeline', path: '/investigations/:id/timeline', hint: 'Filter events by date, entity, type or evidence source; open any event.' },
  { label: 'Contradiction', path: '/investigations/:id/intelligence?tab=contradictions', hint: 'Conflicting evidence compared, confidence revised, provenance on demand.' },
  { label: 'Hypotheses', path: '/investigations/:id/intelligence?tab=hypotheses', hint: 'Competing explanations weighed side by side — never a single narrative.' },
  { label: 'Evidence Impact', path: '/investigations/:id/intelligence?tab=simulator', hint: 'Simulate removing a record — labelled SIMULATION, case data untouched.' },
  { label: 'Copilot', path: '/investigations/:id?copilot=1', hint: 'Ask about connections, contradictions, changes or gaps. Mock responses, streaming-ready.' },
];

export function DemoModeTour() {
  const navigate = useNavigate();
  const [active, setActive] = useState(() => storage.getItem(KEY) === 'active');
  const [step, setStep] = useState(0);
  const [caseId, setCaseId] = useState(null);

  const stop = useCallback(() => {
    setActive(false);
    storage.setItem(KEY, 'off');
  }, []);

  useEffect(() => {
    const onStart = () => {
      storage.setItem(KEY, 'active');
      setStep(0);
      setActive(true);
    };
    window.addEventListener(DEMO_TOUR_EVENT, onStart);
    return () => window.removeEventListener(DEMO_TOUR_EVENT, onStart);
  }, []);

  // Resolve a case id once for case-scoped steps.
  useEffect(() => {
    if (!active || caseId) return undefined;
    let cancel = false;
    investigationService
      .list({ status: 'active' })
      .then((r) => {
        if (!cancel) setCaseId(r.items[0]?.id || null);
      })
      .catch(() => setCaseId(null));
    return () => {
      cancel = true;
    };
  }, [active, caseId]);

  const current = STEPS[step];
  const target = current.path.replace(':id', caseId || '');

  useEffect(() => {
    if (!active || !target) return undefined;
    navigate(target);
    return undefined;
  }, [active, step, target]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!active) return null;

  return (
    <div className="fixed bottom-4 left-4 z-[90] w-[330px] max-w-[calc(100vw-2rem)] rounded-xl border border-teal-200 bg-white p-3.5 shadow-dropdown animate-fade-in">
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-teal-700">
          <Sparkles className="h-3.5 w-3.5" aria-hidden /> Demo Mode · step {step + 1}/{STEPS.length}
        </p>
        <button type="button" onClick={stop} aria-label="Exit demo mode" className="rounded p-1 text-navy-300 hover:text-navy-600">
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <p className="mt-1.5 text-[13.5px] font-semibold text-navy-900">{current.label}</p>
      <p className="mt-1 text-[12px] leading-relaxed text-navy-500">{current.hint}</p>
      <div className="mt-3 flex items-center gap-2">
        <Button variant="outline" size="sm" icon={ChevronLeft} disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
          Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button size="sm" onClick={() => setStep((s) => s + 1)}>
            Next
          </Button>
        ) : (
          <Button size="sm" onClick={stop}>
            Finish tour
          </Button>
        )}
        {!caseId && current.path.includes(':id') && <span className="text-[11px] text-navy-300">Loading case…</span>}
      </div>
    </div>
  );
}
