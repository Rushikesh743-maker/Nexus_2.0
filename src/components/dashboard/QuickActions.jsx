import { useNavigate } from 'react-router-dom';
import { Plus, Upload, Share2, History } from 'lucide-react';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';

const ACTIONS = [
  { id: 'create', label: 'Create Investigation', icon: Plus, tone: 'bg-teal-600 text-white' },
  { id: 'upload', label: 'Upload Evidence', icon: Upload, tone: 'bg-sky-50 text-sky-700' },
  { id: 'network', label: 'View Network', icon: Share2, tone: 'bg-violet-50 text-violet-700' },
  { id: 'timeline', label: 'View Timeline', icon: History, tone: 'bg-amber-50 text-amber-700' },
];

/** Dashboard quick actions. Case-scoped actions open the case picker first. */
export function QuickActions({ onPickCase }) {
  const navigate = useNavigate();

  const handle = (id) => {
    if (id === 'create') {
      navigate('/investigations/new');
      return;
    }
    onPickCase(id);
  };

  return (
    <Card>
      <CardHeader title="Quick actions" />
      <CardBody className="grid grid-cols-2 gap-2.5">
        {ACTIONS.map((action) => (
          <button
            key={action.id}
            type="button"
            onClick={() => handle(action.id)}
            className="flex flex-col items-start gap-2.5 rounded-xl border border-slate-200 p-3 text-left transition-colors hover:border-teal-300 hover:bg-teal-50/40"
          >
            <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${action.tone}`}>
              <action.icon className="h-4 w-4" aria-hidden />
            </span>
            <span className="text-[12.5px] font-medium leading-tight text-navy-700">{action.label}</span>
          </button>
        ))}
      </CardBody>
    </Card>
  );
}
