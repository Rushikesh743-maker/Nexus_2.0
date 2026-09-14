import { useCallback, useMemo, useState } from 'react';
import { Camera, GitCompareArrows, History } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageLoader } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { useToast } from '@/context/ToastContext';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService, V1Error } from '@/services/v1';
import { FreshnessBadge } from '@/components/cases/FreshnessBadge';
import { useCaseFile } from './CaseLayout';
import { cn, formatDateTime } from '@/lib/utils';

const SECTIONS = [
  { key: 'entities', label: 'Entities' },
  { key: 'relationships', label: 'Relationships' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'locations', label: 'Locations' },
  { key: 'findings', label: 'Findings' },
  { key: 'hypotheses', label: 'Hypotheses' },
];

function rowLabel(section, row) {
  if (section === 'entities') return `#${row.id} ${row.canonical_name} (${row.entity_type})`;
  if (section === 'relationships') return `#${row.id} ${row.source_name} —${row.relationship_type}→ ${row.target_name}`;
  if (section === 'evidence') return `#${row.id} ${row.evidence_type}${row.description ? ` — ${row.description}` : ''}`;
  if (section === 'locations') return `#${row.id} ${row.name}`;
  if (section === 'findings') return `#${row.id} [${row.finding_type}] ${row.title}`;
  if (section === 'hypotheses') return `#${row.id} [${row.hypothesis_type}] ${row.title}`;
  return `#${row.id}`;
}

function DiffSection({ section, diff }) {
  const total = (diff.added?.length || 0) + (diff.removed?.length || 0) + (diff.changed?.length || 0);
  if (total === 0) return null;
  return (
    <div>
      <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-navy-400">
        {SECTIONS.find((s) => s.key === section)?.label || section}
      </p>
      <ul className="space-y-0.5">
        {(diff.added || []).map((r) => (
          <li key={`a${r.id}`} className="flex items-start gap-1.5 text-[12px] text-emerald-700">
            <span className="figure mt-px w-4 shrink-0">+</span>
            <span>{rowLabel(section, r)}</span>
          </li>
        ))}
        {(diff.removed || []).map((r) => (
          <li key={`r${r.id}`} className="flex items-start gap-1.5 text-[12px] text-rose-700">
            <span className="figure mt-px w-4 shrink-0">−</span>
            <span>{rowLabel(section, r)}</span>
          </li>
        ))}
        {(diff.changed || []).map((r) => (
          <li key={`c${r.id}`} className="flex items-start gap-1.5 text-[12px] text-amber-700">
            <span className="figure mt-px w-4 shrink-0">~</span>
            <span>
              {rowLabel(section, { id: r.id })}
              <span className="text-navy-500">
                {Object.entries(r.fields || {}).map(([f, v]) => (
                  <span key={f} className="ml-1.5">
                    {f}: <s>{String(v.from ?? '—')}</s> → {String(v.to ?? '—')}
                  </span>
                ))}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Case snapshots (phase 2, work item D+G): immutable version 1..N captures
 * of the case's confirmed state, with a pure N → N+1 compare ("what
 * changed"). Capture is one click; nothing here can edit or delete a
 * snapshot — the list is the audit trail of how the case's confirmed data
 * moved over time.
 */
export function CaseSnapshotsPage() {
  const { caseFile: c } = useCaseFile();
  const toast = useToast();
  const [reloadKey, setReloadKey] = useState(0);
  const [label, setLabel] = useState('');
  const [capturing, setCapturing] = useState(false);
  const [fromSeq, setFromSeq] = useState(null);
  const [toSeq, setToSeq] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [compareData, setCompareData] = useState(null);

  const { data, error, loading, reload } = useCnaResource(
    useCallback(() => caseService.listSnapshots(c.id), [c.id, reloadKey]),
    [c.id, reloadKey]
  );
  const snaps = useMemo(() => (data?.snapshots || []), [data]);

  const capture = async () => {
    setCapturing(true);
    try {
      const s = await caseService.createSnapshot(c.id, label.trim() || undefined);
      toast.success(`Snapshot ${s.sequence} captured (${s.entity_count} entities / ${s.relationship_count} relationships / ${s.evidence_count} evidence).`);
      setLabel('');
      setReloadKey((k) => k + 1);
    } catch (e) {
      toast.error(e.message || 'Snapshot capture failed.');
    } finally {
      setCapturing(false);
    }
  };

  const compare = useCallback(async () => {
    if (fromSeq == null || toSeq == null) return;
    setComparing(true);
    setCompareData(null);
    try {
      const d = await caseService.compareSnapshots(c.id, fromSeq, toSeq);
      setCompareData(d);
    } catch (e) {
      if (e instanceof V1Error && e.code === 'SNAPSHOT_COMPARE_INVALID') {
        toast.error(e.message);
      } else {
        toast.error(e.message || 'Compare failed.');
      }
    } finally {
      setComparing(false);
    }
  }, [c.id, fromSeq, toSeq, toast]);

  if (loading && !data) return <PageLoader label="Loading snapshots…" />;
  if (error && !data) return <ErrorState title="Snapshots unavailable" description={error.message} onRetry={reload} />;

  const currentVersion = data?.current_graph_version || '';
  const latest = snaps[snaps.length - 1];
  const behind = latest && latest.graph_version !== currentVersion;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-[17px] text-navy-900">Snapshots</h2>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="figure text-[11px] text-navy-400">
              current version {currentVersion.slice(0, 12)}…
            </span>
            <FreshnessBadge analysis={data?.analysis} />
            {behind && (
              <Badge variant="warning" title="Confirmed data changed since the last capture.">
                last capture is behind
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (optional)"
            maxLength={255}
            className="h-8 w-44 rounded-md border border-line bg-surface px-2.5 text-[12.5px] text-navy-800 outline-none placeholder:text-navy-300 focus:border-line-strong"
          />
          <Button size="md" icon={Camera} loading={capturing} onClick={capture}>
            Capture snapshot
          </Button>
        </div>
      </div>

      {snaps.length === 0 ? (
        <EmptyState
          icon={History}
          title="No snapshots yet"
          description="Capture the case's confirmed state as immutable version 1 — later captures can be compared against it to see exactly what changed."
        />
      ) : (
        <Card>
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wide text-navy-400">
                <th className="px-4 py-2.5 font-semibold">#</th>
                <th className="px-3 py-2.5 font-semibold">Label</th>
                <th className="px-3 py-2.5 text-right font-semibold">Entities</th>
                <th className="px-3 py-2.5 text-right font-semibold">Relations</th>
                <th className="px-3 py-2.5 text-right font-semibold">Evidence</th>
                <th className="px-3 py-2.5 font-semibold">Version</th>
                <th className="px-3 py-2.5 font-semibold">Captured</th>
              </tr>
            </thead>
            <tbody>
              {snaps.map((s) => (
                <tr key={s.id} className={cn('border-b border-line-soft last:border-0', latest && s.id === latest.id && 'bg-surface-sunken/40')}>
                  <td className="figure px-4 py-2.5 text-navy-700">{s.sequence}</td>
                  <td className="px-3 py-2.5 text-navy-800">{s.label || <span className="text-navy-300">—</span>}</td>
                  <td className="figure px-3 py-2.5 text-right text-navy-600">{s.entity_count}</td>
                  <td className="figure px-3 py-2.5 text-right text-navy-600">{s.relationship_count}</td>
                  <td className="figure px-3 py-2.5 text-right text-navy-600">{s.evidence_count}</td>
                  <td className="px-3 py-2.5">
                    <span
                      className="figure text-[11px] text-navy-500"
                      title={s.graph_version === currentVersion ? 'matches the current confirmed-data version' : 'confirmed data has moved on since this capture'}
                    >
                      {s.graph_version.slice(0, 12)}…
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-navy-400">
                    {formatDateTime(s.created_at)}
                    {s.created_by_name && <span className="block text-[10.5px]">{s.created_by_name}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {snaps.length >= 2 && (
        <Card>
          <CardHeader
            title="Compare two versions"
            actions={
              <div className="flex items-center gap-2">
                <select
                  value={fromSeq ?? ''}
                  onChange={(e) => setFromSeq(e.target.value ? Number(e.target.value) : null)}
                  className="h-7 rounded-md border border-line bg-surface px-2 text-[12px] text-navy-700"
                >
                  <option value="">from…</option>
                  {snaps.map((s) => <option key={s.id} value={s.sequence}>#{s.sequence}{s.label ? ` — ${s.label}` : ''}</option>)}
                </select>
                <span className="text-[12px] text-navy-400">→</span>
                <select
                  value={toSeq ?? ''}
                  onChange={(e) => setToSeq(e.target.value ? Number(e.target.value) : null)}
                  className="h-7 rounded-md border border-line bg-surface px-2 text-[12px] text-navy-700"
                >
                  <option value="">to…</option>
                  {snaps.map((s) => <option key={s.id} value={s.sequence}>#{s.sequence}{s.label ? ` — ${s.label}` : ''}</option>)}
                </select>
                <Button size="sm" icon={GitCompareArrows} loading={comparing} disabled={fromSeq == null || toSeq == null || fromSeq === toSeq} onClick={compare}>
                  Compare
                </Button>
              </div>
            }
          />
          {!compareData ? (
            <p className="px-4 py-3 text-[12px] text-navy-400">
              Pick a “from” and a “to” version — the compare is a pure diff of the two immutable
              payloads (added / removed / changed), never a re-derivation.
            </p>
          ) : (
            <div className="space-y-3 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2 text-[12px] text-navy-600">
                <Badge variant="neutral">#{compareData.from.sequence} → #{compareData.to.sequence}</Badge>
                {SECTIONS.map(({ key, label }) => {
                  const a = compareData.summary?.[`${key}_added`] || 0;
                  const r = compareData.summary?.[`${key}_removed`] || 0;
                  const ch = compareData.summary?.[`${key}_changed`] || 0;
                  if (!a && !r && !ch) return null;
                  return (
                    <Badge key={key} variant="default">
                      {label}: +{a} / −{r} / ~{ch}
                    </Badge>
                  );
                })}
                {(() => {
                  const s = compareData.summary || {};
                  const none = SECTIONS.every(({ key }) => !(s[`${key}_added`] || s[`${key}_removed`] || s[`${key}_changed`]));
                  return none ? <span className="text-navy-400">No changes between these versions.</span> : null;
                })()}
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {SECTIONS.map(({ key }) => (
                  <DiffSection key={key} section={key} diff={compareData[key] || {}} />
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export default CaseSnapshotsPage;
