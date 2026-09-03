import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Lock, ArrowRight } from 'lucide-react';
import { Logo } from '@/components/ui/Logo';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { authService, USE_MOCK_API } from '@/services';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

/**
 * What the platform actually does, stated as capabilities rather than claims.
 * Set as a numbered index — it reads as a contents page, which suits the
 * editorial voice and avoids a row of decorative feature icons.
 */
const CAPABILITIES = [
  ['01', 'Case & evidence', 'Custody chains, review status, source records.'],
  ['02', 'Link analysis', 'Entities and relationships, each carrying its provenance.'],
  ['03', 'Geospatial & temporal', 'Locations, movement, and the network replayed over time.'],
  ['04', 'Reporting', 'Court-ready documents with a verifiable digest.'],
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
    <div className="nexus-grain flex min-h-screen bg-ground">
      {/* ── Editorial panel ─────────────────────────────────────────────── */}
      <aside className="relative z-[1] hidden w-[44%] flex-col justify-between border-r border-line bg-surface p-10 xl:p-14 lg:flex">
        {/* A faint network, drawn once, as the page's only illustration. */}
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden
          style={{
            maskImage: 'radial-gradient(120% 80% at 88% 12%, #000 0%, transparent 62%)',
            WebkitMaskImage: 'radial-gradient(120% 80% at 88% 12%, #000 0%, transparent 62%)',
          }}
        >
          <defs>
            <pattern id="nexus-net" width="96" height="96" patternUnits="userSpaceOnUse">
              <path
                d="M16 16 78 40M78 40 36 78M36 78 16 16"
                stroke="currentColor"
                strokeWidth="0.75"
                fill="none"
                className="text-navy-900"
                opacity="0.09"
              />
              <circle cx="16" cy="16" r="2" className="fill-navy-900" opacity="0.11" />
              <circle cx="78" cy="40" r="1.6" className="fill-navy-900" opacity="0.08" />
              <circle cx="36" cy="78" r="1.6" className="fill-navy-900" opacity="0.08" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#nexus-net)" />
        </svg>

        <Logo withTagline className="relative" />

        <div className="relative max-w-lg">
          <h1 className="font-display text-[40px] leading-[1.08] tracking-[-0.015em] text-navy-900 xl:text-[46px]">
            Connect the dots across cases, evidence and networks.
          </h1>
          <p className="mt-5 max-w-md text-[13.5px] leading-relaxed text-navy-500">
            A single workspace for investigation teams. Every relationship it draws carries the source record behind
            it — nothing is asserted that cannot be shown.
          </p>

          <ul className="mt-10 divide-y divide-line-soft border-y border-line-soft">
            {CAPABILITIES.map(([n, title, text]) => (
              <li key={n} className="flex items-baseline gap-5 py-3.5">
                <span className="figure w-6 shrink-0 text-[11px] text-navy-300">{n}</span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium text-navy-800">{title}</span>
                  <span className="mt-0.5 block text-[12px] leading-relaxed text-navy-400">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-[11px] text-navy-300">
          Frontend preview · all case data shown in-app is fictional
        </p>
      </aside>

      {/* ── Form panel ──────────────────────────────────────────────────── */}
      <main className="relative z-[1] flex flex-1 flex-col px-6 py-8 sm:px-10">
        <div className="flex items-center justify-between">
          <div className="lg:hidden">
            <Logo />
          </div>
          <ThemeToggle className="ml-auto" />
        </div>

        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-[380px]">
            <p className="label-micro text-navy-400">Investigation Intelligence Platform</p>
            <h2 className="mt-2.5 font-display text-[30px] leading-tight text-navy-900">Sign in</h2>
            <p className="mt-2 text-[13px] text-navy-400">
              Use your department account to open the workspace.
            </p>

            {USE_MOCK_API && (
              <div className="mt-7 rounded-md border border-line bg-slate-50 p-3.5">
                <p className="label-micro text-navy-500">Development environment</p>
                <p className="mt-2 text-[12px] leading-relaxed text-navy-500">
                  Authentication is handled by the frontend mock service — nothing is sent to a server. Production
                  sign-in requires the department identity service.
                </p>
                <button
                  type="button"
                  onClick={fillDemo}
                  className="group mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-navy-800 transition-colors hover:text-accent"
                >
                  Fill demo credentials
                  <ArrowRight
                    className="h-3 w-3 transition-transform duration-200 group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </button>
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-7 space-y-4" noValidate>
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
                  className="absolute right-2 top-[26px] rounded p-1 text-navy-300 transition-colors hover:text-navy-700"
                >
                  {showPassword ? <EyeOff className="h-3.5 w-3.5" aria-hidden /> : <Eye className="h-3.5 w-3.5" aria-hidden />}
                </button>
              </div>

              <Button type="submit" loading={loading} className="w-full" size="lg">
                Sign in
              </Button>
            </form>

            <p className="mt-8 flex items-center justify-center gap-1.5 text-[11px] text-navy-300">
              <Lock className="h-3 w-3" aria-hidden />
              Secure investigation environment · authorised demo use only
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
