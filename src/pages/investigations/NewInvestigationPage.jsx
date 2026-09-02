import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, X, ChevronDown } from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Input, Field } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { Select } from '@/components/ui/Select';
import { Button, buttonClasses } from '@/components/ui/Button';
import { Avatar } from '@/components/ui/Avatar';
import { investigationService } from '@/services';
import { mockUsers } from '@/mock/mockUsers';
import { CASE_TYPE_OPTIONS } from '@/lib/constants';
import { useToast } from '@/context/ToastContext';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { cn } from '@/lib/utils';

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const CASE_TYPE_SELECT_OPTIONS = [{ value: '', label: 'Select' }, ...CASE_TYPE_OPTIONS];

/** The development-only demo account is not a real investigator. */
const PERSONNEL = mockUsers.filter((u) => u.id !== 'usr-demo');

export function NewInvestigationPage() {
  useDocumentTitle('Create New Investigation');
  const navigate = useNavigate();
  const toast = useToast();

  const [form, setForm] = useState({
    title: '',
    caseType: '',
    description: '',
    priority: 'medium',
  });
  const [extraOpen, setExtraOpen] = useState(false);
  const [extra, setExtra] = useState({ leadId: PERSONNEL[0].id, jurisdiction: '', tags: '' });
  const [teamIds, setTeamIds] = useState([]);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const toggleTeamMember = (id) => {
    setTeamIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const nextErrors = {};
    if (form.title.trim().length < 4) nextErrors.title = 'Give the investigation a descriptive name (at least 4 characters).';
    if (!form.caseType) nextErrors.caseType = 'Select a case type.';
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setSaving(true);
    try {
      const investigation = await investigationService.create({
        title: form.title.trim(),
        caseType: form.caseType,
        description: form.description.trim(),
        priority: form.priority,
        leadId: extra.leadId,
        teamIds,
        jurisdiction: extra.jurisdiction.trim(),
        tags: extra.tags
          .split(',')
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
      });
      toast.success('Investigation created', `${investigation.code} · ${investigation.title}`);
      navigate(`/investigations/${investigation.id}`);
    } catch (err) {
      toast.error('Could not create investigation', err.message);
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader
        breadcrumb={[{ label: 'Investigations', to: '/investigations' }, { label: 'Create New Investigation' }]}
        title="Create New Investigation"
        description="Register a case file. Evidence, entities and events attach to it once created."
        actions={
          <Button variant="outline" icon={ArrowLeft} onClick={() => navigate('/investigations')}>
            Cancel
          </Button>
        }
      />

      <Card>
        <CardHeader title="Case details" subtitle="The investigation opens as Active as soon as it is created." />
        <CardBody>
          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            <Input
              label="Investigation Name"
              required
              placeholder="e.g. Operation SafeReturn"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              error={errors.title}
            />
            <Select
              label="Case Type"
              required
              value={form.caseType}
              onChange={(e) => setForm({ ...form, caseType: e.target.value })}
              options={CASE_TYPE_SELECT_OPTIONS}
              error={errors.caseType}
            />
            <Textarea
              label="Description"
              rows={5}
              placeholder="What is being investigated, what is known so far, and what the case should establish…"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              hint="Shown on the case overview for the whole team."
            />
            <div className="sm:w-1/2">
              <Select
                label="Priority"
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
                options={PRIORITY_OPTIONS}
              />
            </div>

            {/* Optional details */}
            <div className="rounded-xl border border-slate-200">
              <button
                type="button"
                onClick={() => setExtraOpen((o) => !o)}
                aria-expanded={extraOpen}
                className="flex w-full items-center justify-between px-4 py-3 text-left"
              >
                <span>
                  <span className="text-[13px] font-medium text-navy-700">Additional details</span>
                  <span className="block text-[11px] text-navy-300">Lead investigator, jurisdiction, tags and team — optional.</span>
                </span>
                <ChevronDown className={cn('h-4 w-4 text-navy-400 transition-transform', extraOpen && 'rotate-180')} aria-hidden />
              </button>
              {extraOpen && (
                <div className="space-y-4 border-t border-slate-100 px-4 py-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Select
                      label="Lead investigator"
                      value={extra.leadId}
                      onChange={(e) => setExtra({ ...extra, leadId: e.target.value })}
                      options={PERSONNEL.map((u) => ({ value: u.id, label: `${u.rank} ${u.name}` }))}
                    />
                    <Input
                      label="Jurisdiction"
                      placeholder="e.g. Pune City"
                      value={extra.jurisdiction}
                      onChange={(e) => setExtra({ ...extra, jurisdiction: e.target.value })}
                    />
                  </div>
                  <Field label="Tags" hint="Comma separated — e.g. kidnapping, transit">
                    <Input placeholder="kidnapping, transit" value={extra.tags} onChange={(e) => setExtra({ ...extra, tags: e.target.value })} />
                  </Field>
                  <Field label="Team" hint="Investigators who will work this case.">
                    <div className="flex flex-wrap gap-2">
                      {PERSONNEL.map((u) => {
                        const selectedMember = teamIds.includes(u.id);
                        return (
                          <button
                            key={u.id}
                            type="button"
                            onClick={() => toggleTeamMember(u.id)}
                            aria-pressed={selectedMember}
                            className={cn(
                              'flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-[13px] font-medium transition-colors',
                              selectedMember
                                ? 'border-teal-600 bg-teal-50 text-teal-800'
                                : 'border-slate-200 bg-white text-navy-500 hover:border-navy-300'
                            )}
                          >
                            <Avatar name={u.name} size="xs" />
                            {u.name}
                            {selectedMember && <X className="h-3 w-3" aria-hidden />}
                          </button>
                        );
                      })}
                    </div>
                  </Field>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <LinkCancel />
              <Button type="submit" icon={Plus} loading={saving}>
                Create Investigation
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}

function LinkCancel() {
  const navigate = useNavigate();
  return (
    <button type="button" className={buttonClasses('outline', 'md')} onClick={() => navigate('/investigations')}>
      Cancel
    </button>
  );
}
