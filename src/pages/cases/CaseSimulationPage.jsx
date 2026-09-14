import { useState } from 'react';
import { FlaskConical, Play } from 'lucide-react';
import { Card, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input, Field } from '@/components/ui/Input';
import { DataTable } from '@/components/tables/DataTable';
import { useCnaResource } from '@/hooks/useCnaResource';
import { caseService } from '@/services/v1';
import { useCaseFile } from './CaseLayout';
import { useToast } from '@/context/ToastContext';
import { formatDateTime } from '@/lib/utils';

/**
 * Evidence impact simulation — foundation stage.
 *
 * Simulation records can be created and listed; the counterfactual engine
 * ("what changes if this evidence is removed?") is explicitly a later stage
 * and is labelled as such rather than faked.
 */
export function CaseSimulationPage() {
  const { caseFile: c } = useCaseFile();
  const toast = useToast();
  const { data: sims, error, loading, reload } = useCnaResource(
    () => caseService.listSimulations(c.id),
    [c.id]
  );
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await caseService.createSimulation(c.id, {
        name: name.trim(),
        description: description.trim() || null,
      });
      toast.success('Simulation scenario recorded.');
      setName('');
      setDescription('');
      reload();
    } catch (err) {
      toast.error(err.message || 'Could not create simulation.');
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {
      key: 'name',
      header: 'Scenario',
      render: (s) => (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-navy-800" title={s.name}>{s.name}</p>
          {s.description && (
            <p className="line-clamp-1 max-w-md text-[11.5px] text-navy-400" title={s.description}>{s.description}</p>
          )}
        </div>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (s) => <span className="text-[11.5px] text-navy-400">{formatDateTime(s.created_at)}</span>,
    },
    {
      key: 'engine',
      header: 'Engine',
      render: () => <Badge variant="neutral">later stage</Badge>,
    },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="New scenario"
          subtitle="Record a counterfactual to evaluate — the impact engine that scores it lands in a later stage"
        />
        <div className="flex flex-col gap-3 p-4 pt-1 md:flex-row md:items-end">
          <div className="flex-1">
            <Field label="Scenario name" required>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. If the Industrial Area sighting is excluded"
              />
            </Field>
          </div>
          <div className="flex-1">
            <Field label="Description">
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What is being tested"
              />
            </Field>
          </div>
          <Button icon={Play} onClick={submit} disabled={saving || !name.trim()}>
            {saving ? 'Saving…' : 'Record scenario'}
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Scenarios"
          subtitle="Recorded for this case"
          actions={<FlaskConical className="h-4 w-4 text-navy-300" aria-hidden />}
        />
        <DataTable
          columns={columns}
          data={sims || []}
          getRowId={(s) => s.id}
          isLoading={loading}
          error={error}
          onRetry={reload}
          emptyIcon={FlaskConical}
          emptyTitle="No scenarios recorded"
          emptyDescription="Record a counterfactual scenario above; the scoring engine arrives in a later stage."
        />
      </Card>
    </div>
  );
}
