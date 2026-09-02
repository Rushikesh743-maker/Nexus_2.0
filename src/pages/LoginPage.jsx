import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Briefcase, Share2, Map as MapIcon, History, Eye, EyeOff, ShieldCheck, Lock } from 'lucide-react';
import { Logo } from '@/components/ui/Logo';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { authService, USE_MOCK_API } from '@/services';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

const HIGHLIGHTS = [
  { icon: Briefcase, title: 'Case & evidence management', text: 'Track investigations, custody chains and review status.' },
  { icon: Share2, title: 'Link & network analysis', text: 'Map entities and relationships across a case.' },
  { icon: MapIcon, title: 'Geospatial review', text: 'Plot crime scenes, meeting points and transit corridors.' },
  { icon: History, title: 'Timelines & reporting', text: 'Reconstruct events and produce case reports.' },
];

export function LoginPage() {
  useDocumentTitle('Sign in');
  const { login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const from = location.state?.from || '/dashboard';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email.trim() || !password) {
      setError('Enter both email and password.');
      return;
    }
    setLoading(true);
    try {
      const user = await login(email, password);
      const first = user.name.split(' ')[0];
      toast.success(
        `Welcome back, ${first.toLowerCase() === 'demo' ? 'Investigator' : first}`,
        'Demo session started (mock authentication).'
      );
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Sign-in failed.');
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = () => {
    const demo = authService.getDemoCredentials();
    setEmail(demo.email);
    setPassword(demo.password);
    setError('');
  };

  return (
    <div className="flex min-h-screen bg-white">
      {/* Brand panel */}
      <aside className="relative hidden w-[46%] flex-col justify-between overflow-hidden bg-navy-900 p-10 xl:p-14 lg:flex">
        <svg className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.07]" aria-hidden>
          <defs>
            <pattern id="net" width="72" height="72" patternUnits="userSpaceOnUse">
              <circle cx="12" cy="12" r="2.5" fill="#2dd4bf" />
              <circle cx="54" cy="30" r="2" fill="#2dd4bf" />
              <circle cx="26" cy="56" r="2" fill="#2dd4bf" />
              <path d="M12 12 54 30M54 30 26 56M26 56 12 12" stroke="#2dd4bf" strokeWidth="1" fill="none" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#net)" />
        </svg>

        <Logo variant="light" withTagline className="relative" />

        <div className="relative max-w-md">
          <h1 className="text-[26px] font-semibold leading-snug text-white">
            Connect the dots across cases, evidence and networks.
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-navy-200/80">
            A single workspace for investigation teams — case files, link analysis, geospatial review and reporting, designed
            for day-to-day investigative work.
          </p>
          <ul className="mt-8 space-y-4">
            {HIGHLIGHTS.map((h) => (
              <li key={h.title} className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-500/15 text-teal-300">
                  <h.icon className="h-4 w-4" aria-hidden />
                </span>
                <span>
                  <span className="block text-sm font-medium text-white">{h.title}</span>
                  <span className="block text-xs text-navy-200/70">{h.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-[11px] text-navy-300/60">
          Frontend preview build · all case data shown in-app is fictional
        </p>
      </aside>

      {/* Form panel */}
      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <div className="lg:hidden">
            <Logo withTagline />
          </div>

          <p className="mt-8 text-[11px] font-semibold uppercase tracking-[0.18em] text-teal-700 lg:mt-0">
            Investigation Intelligence Platform
          </p>
          <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-navy-900">Sign in to NEXUS</h2>
          <p className="mt-1.5 text-sm text-navy-400">Use your department account to open the workspace.</p>

          {USE_MOCK_API && (
            <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs leading-relaxed text-amber-800">
              <p>
                <strong className="font-semibold">Development environment.</strong> Authentication is handled by the frontend
                mock service — nothing is sent to a server. Production sign-in requires the department identity service and is
                not part of this build.
              </p>
              <p className="mt-2">
                Development account: <code className="rounded bg-amber-100 px-1 py-px font-mono">demo-investigator@nexus.local</code>
              </p>
              <button
                type="button"
                onClick={fillDemo}
                className="mt-2 block rounded-md bg-amber-100 px-2 py-1 font-medium text-amber-900 transition-colors hover:bg-amber-200"
              >
                Fill demo credentials
              </button>
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              placeholder="name@unit.gov.in"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={error && !email.trim() ? error : undefined}
            />
            <div className="relative">
              <Input
                label="Password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                error={error || undefined}
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute right-2.5 top-[34px] rounded p-1 text-navy-300 transition-colors hover:text-navy-600"
              >
                {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
              </button>
            </div>
            <Button type="submit" loading={loading} className="w-full" size="lg">
              Sign In
            </Button>
          </form>

          <p className="mt-8 flex items-center justify-center gap-1.5 text-center text-[11px] font-medium text-navy-400">
            <Lock className="h-3.5 w-3.5" aria-hidden />
            Secure investigation environment
          </p>
          <p className="mt-1.5 flex items-center justify-center gap-1.5 text-center text-[11px] text-navy-300">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            Authorised use in demo environments only
          </p>
        </div>
      </main>
    </div>
  );
}
