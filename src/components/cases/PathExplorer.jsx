/**
 * Path explorer (stage 3): pick two confirmed entities and list the
 * confirmed connection paths between them (BFS shortest paths, depth and
 * result count bounded by the engine). Empty state is explicit —
 * "No confirmed connection path found." — never a fake path.
 */
import { useMemo, useState } from 'react';
import { GitBranch, Route } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Spinner } from '@/components/ui/LoadingState';
import { graphService } from '@/services/v1';

export function PathResult({ path, onHighlight }) {
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12.5px]">
        {path.nodes.map((n, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="flex items-center gap-1 font-mono text-[10.5px] text-navy-400">
                <span className="h-px w-3 bg-navy-200" aria-hidden />
                {path.relationship_types[i - 1]}
              </span>
            )}
            <button
              type="button"
              className="font-medium text-navy-700 hover:text-navy-950 hover:underline"
              onClick={() => onHighlight([n.entity_id], `${path.nodes[0].name} → ${path.nodes[path.nodes.length - 1].name}`)}
            >
              {n.name}
            </button>
          </span>
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <Badge variant="neutral">{path.path_length} hop{path.path_length === 1 ? '' : 's'}</Badge>
        <Badge variant={path.evidence_count > 0 ? 'teal' : 'neutral'}>
          {path.evidence_count} linked evidence record{path.evidence_count === 1 ? '' : 's'}
        </Badge>
        <span className="text-[11px] text-navy-400">analytical context, not proof</span>
      </div>
    </li>
  );
}

export function PathExplorer({ caseId, entities, onHighlight }) {
  const [source, setSource] = useState('');
  const [target, setTarget] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // null = not searched

  const options = useMemo(
    () => [...entities].sort((a, b) => a.name.localeCompare(b.name)),
    [entities]
  );

  const search = async () => {
    if (!source || !target) return;
    setLoading(true);
    setError(null);
    try {
      const res = await graphService.findGraphPaths(caseId, source, target);
      setResult(res);
    } catch (err) {
      if (err.code === 'PATH_NOT_FOUND') {
        setResult({ paths: [], message: err.message });
      } else {
        setError(err);
        setResult(null);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Path Explorer"
        subtitle="Confirmed connections between two entities"
        actions={
          <Button
            size="sm"
            icon={GitBranch}
            loading={loading}
            disabled={!source || !target || source === target}
            onClick={search}
          >
            Find paths
          </Button>
        }
      />
      <div className="space-y-2.5 border-b border-line-soft px-4 py-3">
        <div className="grid grid-cols-2 gap-2.5">
          <label className="block">
            <span className="label-micro">Entity A</span>
            <select
              className="mt-1 w-full rounded border border-line bg-surface px-2 py-1.5 text-[12.5px] text-navy-800"
              value={source}
              onChange={(e) => { setSource(e.target.value); setResult(null); }}
            >
              <option value="">Select…</option>
              {options.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label-micro">Entity B</span>
            <select
              className="mt-1 w-full rounded border border-line bg-surface px-2 py-1.5 text-[12.5px] text-navy-800"
              value={target}
              onChange={(e) => { setTarget(e.target.value); setResult(null); }}
            >
              <option value="">Select…</option>
              {options.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </label>
        </div>
        {source && target && source === target && (
          <p className="text-[11.5px] text-navy-400">Pick two different entities.</p>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-navy-400">
          <Spinner className="h-4 w-4" /> Searching confirmed paths…
        </div>
      ) : error ? (
        <ErrorState compact title="Path search failed" description={error.message} />
      ) : !result ? (
        <EmptyState
          compact
          icon={Route}
          title="No search yet"
          description="Select two entities to find their confirmed connection paths (bounded depth, shortest paths only)."
        />
      ) : result.paths.length === 0 ? (
        <EmptyState
          compact
          icon={Route}
          title="No confirmed connection path found"
          description={result.message || 'The confirmed graph has no path between these entities within the depth limit.'}
        />
      ) : (
        <ul className="max-h-[300px] divide-y divide-line-soft overflow-y-auto">
          {result.paths.map((p, i) => (
            <PathResult key={i} path={p} onHighlight={onHighlight} />
          ))}
        </ul>
      )}
    </Card>
  );
}
