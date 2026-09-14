import { supabase, isSupabaseConfigured, getAccessToken } from '@/lib/supabase';
import { me as v1Me } from './v1/authService';

/**
 * Authentication — Supabase Auth.
 *
 * The React client signs in against Supabase (email/password). The Supabase
 * access token is what every protected NEXUS request carries; the platform
 * backend verifies it and returns the NEXUS profile + role from
 * `GET /api/v1/auth/me` (resolved from the verified identity — a client can
 * never assert its own role). There is no mock login path and no demo
 * credential. If Supabase is not configured, sign-in reports that plainly
 * instead of falling back to anything.
 */

export function isSupabaseReady() {
  return isSupabaseConfigured;
}

/** The current Supabase access token, or null when signed out. */
export { getAccessToken };

function friendlyAuthError(error) {
  if (!isSupabaseConfigured) {
    return 'Sign-in is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY, then create the account in Supabase Auth.';
  }
  const msg = (error?.message || 'Sign-in failed.').replace(/\s+/g, ' ').trim();
  // Supabase reports bad credentials as "Invalid login credentials".
  if (/invalid login credentials/i.test(msg)) return 'Invalid email or password.';
  if (/user not found/i.test(msg)) return 'No account with that email.';
  if (/email not confirmed/i.test(msg)) return 'Your email is not confirmed yet.';
  if (/rate limit/i.test(msg)) return 'Too many attempts. Try again in a moment.';
  return msg;
}

/**
 * Sign in with email + password. On success the Supabase session is persisted
 * (and auto-refreshed) by supabase-js; we then fetch the NEXUS profile so the
 * caller has the name + role immediately.
 *
 * @returns {Promise<object>} the NEXUS profile ({ id, name, email, role, ... })
 */
export async function login({ email, password }) {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: String(email).trim(),
    password,
  });
  if (error) {
    console.error('Supabase login error', error);
    const e = new Error(error.message);
    e.status = error.status;
    e.code = error.code;
    e.name = error.name;
    throw e;
  }
  if (!data.session?.access_token) throw new Error('Sign-in did not return a session.');
  const profile = await v1Me();
  return profile;
}

/**
 * Sign up a new user with email + password.
 * Returns the NEXUS profile after the account is created and the user is logged in.
 */
export async function signUp({ name, email, password }) {
  const { data, error } = await supabase.auth.signUp({
    email: String(email).trim(),
    password,
    data: name ? { full_name: name } : undefined,
  });
  if (error) throw new Error(friendlyAuthError(error));
  // Supabase may require email confirmation – the session may be null until verified.
  // If a session is returned, fetch the NEXUS profile immediately.
  if (data.session?.access_token) {
    const profile = await v1Me();
    return profile;
  }
  // No session yet (e.g., email not confirmed). Return a minimal placeholder.
  return null;
}

/**
 * The current NEXUS profile, or null when there is no valid session. Used on
 * app start to restore the user. The profile is re-fetched so the role the
 * backend currently assigns is always what the UI acts on.
 */
export async function getSession() {
  const token = await getAccessToken();
  if (!token) return null;
  try {
    return await v1Me();
  } catch {
    return null;
  }
}

export async function logout() {
  await supabase.auth.signOut();
}

/**
 * Subscribe to Supabase auth state changes (sign in / out / token refresh /
 * user switch). Returns an unsubscribe function.
 */
export function onAuthChange(callback) {
  const { data } = supabase.auth.onAuthStateChange((event, session) => {
    callback({ event, session: session ?? null });
  });
  return () => data.subscription.unsubscribe();
}

export default {
  isSupabaseReady,
  getAccessToken,
  login,
  signUp,
  getSession,
  logout,
  onAuthChange,
};
