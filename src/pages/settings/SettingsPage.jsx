import { useState } from 'react';
import { User, ShieldCheck, SlidersHorizontal, Database, Bell } from 'lucide-react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardHeader, CardBody } from '@/components/ui/Card';
import { Tabs } from '@/components/ui/Tabs';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { API_BASE_URL, USE_MOCK_API } from '@/services/api';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { storage } from '@/lib/storage';
import { cn } from '@/lib/utils';

const PREFS_KEY = 'nexus.preferences';

function loadPrefs() {
  try {
    return { defaultLanding: '/dashboard', pageSize: '8', collapsedSidebar: false, notifyEvidence: true, notifyContradictions: true, notifyMatches: true, ...JSON.parse(storage.getItem(PREFS_KEY)) };
  } catch {
    return { defaultLanding: '/dashboard', pageSize: '8', collapsedSidebar: false, notifyEvidence: true, notifyContradictions: true, notifyMatches: true };
  }
}

function Switch({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-6 w-11 shrink-0 rounded-full transition-colors',
        checked ? 'bg-teal-600' : 'bg-slate-300'
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-[22px]' : 'translate-x-0.5'
        )}
      />
    </button>
  );
}

export function SettingsPage() {
  useDocumentTitle('Settings');
  const { user } = useAuth();
  const toast = useToast();

  const [tab, setTab] = useState('profile');
  const [profile, setProfile] = useState({
    name: user?.name || '',
    email: user?.email || '',
    role: user?.role || '',
    unit: user?.unit || '',
  });
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' });
  const [prefs, setPrefs] = useState(loadPrefs);

  const savePrefs = () => {
    storage.setItem(PREFS_KEY, JSON.stringify(prefs));
    toast.success('Preferences saved', 'Applied to this device.');
  };

  const handlePasswordSubmit = (e) => {
    e.preventDefault();
    if (!passwords.current || !passwords.next || !passwords.confirm) {
      toast.warning('Fill in all password fields first.');
      return;
    }
    if (passwords.next !== passwords.confirm) {
      toast.warning('New passwords do not match.');
      return;
    }
    setPasswords({ current: '', next: '', confirm: '' });
    toast.info('Password changes need the identity service', 'Authentication is mocked in this frontend-only build.');
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Profile, security and workspace preferences. Changes are local to this demo build."
      />

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'profile', label: 'Profile', icon: User },
          { id: 'security', label: 'Security', icon: ShieldCheck },
          { id: 'notifications', label: 'Notifications', icon: Bell },
          { id: 'preferences', label: 'Interface', icon: SlidersHorizontal },
          { id: 'data', label: 'Data Preferences', icon: Database },
        ]}
      />

      {tab === 'profile' && (
        <Card className="max-w-2xl">
          <CardHeader title="Profile" subtitle="Visible to your unit once the identity service is connected." />
          <CardBody>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                toast.info('Profile changes are local to the demo', 'Profile data will sync via the backend API.');
              }}
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Input label="Full name" value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
                <Input label="Email" type="email" value={profile.email} disabled hint="Managed by the identity service" />
                <Input label="Role" value={profile.role} onChange={(e) => setProfile({ ...profile, role: e.target.value })} />
                <Input label="Unit" value={profile.unit} onChange={(e) => setProfile({ ...profile, unit: e.target.value })} />
              </div>
              <Button type="submit">Save profile</Button>
            </form>
          </CardBody>
        </Card>
      )}

      {tab === 'security' && (
        <Card className="max-w-2xl">
          <CardHeader title="Change password" subtitle="Requires the backend identity service." />
          <CardBody>
            <form className="space-y-4" onSubmit={handlePasswordSubmit}>
              <Input
                label="Current password"
                type="password"
                autoComplete="current-password"
                value={passwords.current}
                onChange={(e) => setPasswords({ ...passwords, current: e.target.value })}
              />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Input
                  label="New password"
                  type="password"
                  autoComplete="new-password"
                  value={passwords.next}
                  onChange={(e) => setPasswords({ ...passwords, next: e.target.value })}
                />
                <Input
                  label="Confirm new password"
                  type="password"
                  autoComplete="new-password"
                  value={passwords.confirm}
                  onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })}
                />
              </div>
              <Button type="submit" variant="secondary">
                Update password
              </Button>
            </form>
          </CardBody>
        </Card>
      )}

      {tab === 'notifications' && (
        <Card className="max-w-2xl">
          <CardHeader title="Notifications" subtitle="Choose which case events notify you. Stored per device in this build." />
          <CardBody className="space-y-3">
            {[
              { key: 'notifyEvidence', label: 'Evidence processed', detail: 'When an uploaded file finishes processing.' },
              { key: 'notifyContradictions', label: 'Contradictions detected', detail: 'When conflicting evidence affects a relationship.' },
              { key: 'notifyMatches', label: 'Entity matches to review', detail: 'When a possible identity match needs analyst review.' },
            ].map((row) => (
              <div key={row.key} className="flex items-center justify-between rounded-lg border border-slate-200 p-3.5">
                <div>
                  <p className="text-[13px] font-medium text-navy-700">{row.label}</p>
                  <p className="text-xs text-navy-400">{row.detail}</p>
                </div>
                <Switch
                  label={row.label}
                  checked={prefs[row.key] !== false}
                  onChange={(v) => setPrefs({ ...prefs, [row.key]: v })}
                />
              </div>
            ))}
            <Button onClick={savePrefs}>Save preferences</Button>
          </CardBody>
        </Card>
      )}

      {tab === 'preferences' && (
        <Card className="max-w-2xl">
          <CardHeader title="Workspace preferences" subtitle="Stored per device." />
          <CardBody className="space-y-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Select
                label="Default landing page"
                value={prefs.defaultLanding}
                onChange={(e) => setPrefs({ ...prefs, defaultLanding: e.target.value })}
                options={[
                  { value: '/dashboard', label: 'Dashboard' },
                  { value: '/investigations', label: 'Investigations' },
                ]}
              />
              <Select
                label="Rows per page"
                value={prefs.pageSize}
                onChange={(e) => setPrefs({ ...prefs, pageSize: e.target.value })}
                options={[
                  { value: '8', label: '8 rows' },
                  { value: '15', label: '15 rows' },
                  { value: '25', label: '25 rows' },
                ]}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3.5">
              <div>
                <p className="text-[13px] font-medium text-navy-700">Start with sidebar collapsed</p>
                <p className="text-xs text-navy-400">Applies on next page load on desktop.</p>
              </div>
              <Switch
                label="Start with sidebar collapsed"
                checked={prefs.collapsedSidebar}
                onChange={(v) => setPrefs({ ...prefs, collapsedSidebar: v })}
              />
            </div>
            <Button onClick={savePrefs}>Save preferences</Button>
          </CardBody>
        </Card>
      )}

      {tab === 'data' && (
        <Card className="max-w-2xl">
          <CardHeader title="Data Preferences" subtitle="How this build gets its data." />
          <CardBody className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3.5">
              <span className="text-[13px] font-medium text-navy-700">Current mode</span>
              <Badge variant={USE_MOCK_API ? 'warning' : 'success'} dot>
                {USE_MOCK_API ? 'Mock data' : 'Live API'}
              </Badge>
              <span className="ml-auto font-mono text-[12px] text-navy-400">{API_BASE_URL}</span>
            </div>
            <div className="text-[13px] leading-relaxed text-navy-500">
              <p>
                All screens read through the service layer (<code className="rounded bg-slate-100 px-1 font-mono text-[12px]">src/services</code>
                ). In mock mode the services resolve fictional data with simulated latency; in API mode they call the REST backend
                through a shared Axios client with session-token headers and normalised errors.
              </p>
              <p className="mt-2">To switch once the backend exists:</p>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-navy-900 p-3.5 font-mono text-[12px] leading-relaxed text-teal-200">
{`# .env
VITE_API_BASE_URL=https://api.example.gov.in/v1
VITE_USE_MOCK_API=false`}
              </pre>
              <p className="mt-2 text-navy-400">No UI code changes are required — endpoints map 1:1 to the service functions.</p>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
