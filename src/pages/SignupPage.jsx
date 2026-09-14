import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, AlertTriangle, Lock } from 'lucide-react';
import { Logo } from '@/components/ui/Logo';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { authService } from '@/services';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
const CAPABILITIES = [
  ['01', 'Case & evidence', 'Custody chains, review status, source records.'],
  ['02', 'Link analysis', 'Entities and relationships, each carrying its provenance.'],
  ['03', 'Geospatial & temporal', "Locations, movement, and the network replayed over time."],
  ['04', 'Reporting', 'Court-ready documents with a verifiable digest.'],
];

/**
 * SignupPage – registers a new user via Supabase Auth.
 * On successful sign‑up (and immediate session) the user is redirected to the dashboard.
 * If email confirmation is required, a friendly message is shown.
 */
export function SignupPage() {
  useDocumentTitle('Sign up');
  const navigate = useNavigate();
  const { signup, setUser } = useAuth();
  const toast = useToast();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const profile = await signup({ name, email, password });
      // If a profile is returned we have an active session.
      if (profile) {
        setUser(profile);
        navigate('/dashboard');
        toast.success('Welcome!');
      } else {
        // No session – likely email confirmation required.
        toast.info('Sign‑up successful. Please check your email to confirm your account before signing in.');
        navigate('/login');
      }
    } catch (err) {
      toast.error(err.message || 'Sign‑up failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="nexus-grain flex min-h-screen bg-ground">
      {/* Editorial panel */}
      <aside className="relative z-[1] hidden w-[44%] flex-col justify-between border-r border-line bg-surface p-10 xl:p-14 lg:flex">
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
            A single workspace for investigation teams. Every relationship it draws carries the source record behind it — nothing is asserted that cannot be shown.
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

      {/* Form panel */}
      <main className="relative z-[1] flex flex-1 flex-col px-6 py-8 sm:px-10">
        <div className="flex items-center justify-between">
          <div className="lg:hidden"><Logo /></div>
          <ThemeToggle className="ml-auto" />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-[380px]">
            <p className="label-micro text-navy-400">Investigation Intelligence Platform</p>
            <h2 className="mt-2.5 font-display text-[30px] leading-tight text-navy-900">Create your account</h2>
            <p className="mt-2 text-[13px] text-navy-400">Fill in the details below to get started.</p>
            {!authService.isSupabaseReady() && (
              <div className="mt-7 flex items-start gap-2.5 rounded-md border border-amber-300 bg-amber-50 p-3.5">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
                <p className="text-[12px] leading-relaxed text-amber-800">
                  Sign‑up is not configured. Set <code className="font-mono">VITE_SUPABASE_URL</code> and{' '}
                  <code className="font-mono">VITE_SUPABASE_ANON_KEY</code>, create the account in Supabase Auth,
                  and map it to a NEXUS user (see the README).
                </p>
              </div>
            )}
            <form onSubmit={handleSubmit} className="mt-7 space-y-4" noValidate>
              <Input
                label="Full name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                error={error && !name.trim() ? error : undefined}
              />
              <Input
                label="Email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                error={error && !email.trim() ? error : undefined}
              />
              <div className="relative">
                <Input
                  label="Password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
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
              <Input
                label="Confirm password"
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <Button type="submit" loading={loading} className="w-full" size="lg">
                Sign up
              </Button>
            </form>
            <p className="mt-4 text-center text-sm text-gray-600">
              Already have an account?{' '}<a href="/login" className="font-medium text-indigo-600 hover:text-indigo-500">Sign in</a>
            </p>
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
