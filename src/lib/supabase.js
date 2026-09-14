/**
 * Supabase Auth client (the single source of authentication identity).
 *
 * NEXUS uses Supabase Auth for sign-in. The access token Supabase issues is
 * the bearer token every protected NEXUS request carries (the platform API in
 * `/api/v1` and the analysis backend in `/cna-api`). The NEXUS profile + role
 * come from the platform backend, which resolves the verified token to the
 * NEXUS user — the client never asserts a role.
 *
 * Only the public (anon / publishable) key is used here. It is safe in the
 * browser and is scoped by Supabase RLS. The service-role key must never be
 * referenced from frontend code.
 */
import { createClient } from '@supabase/supabase-js';

// Temporary diagnostic – prints Supabase config presence (will be removed later)
console.log('Supabase URL:', import.meta.env.VITE_SUPABASE_URL);
console.log('Supabase ANON KEY present?', Boolean(import.meta.env.VITE_SUPABASE_ANON_KEY));

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

/** True when both the project URL and the anon key are provided. */
export const isSupabaseConfigured = Boolean(url && anonKey);

/**
 * The client is always created so the rest of the app has a stable import.
 * When unconfigured it is pointed at a placeholder origin, in which case auth
 * calls fail with a clear error (handled in `services/authService.js`) rather
 * than crashing at import time.
 */
export const supabase = createClient(
  url || 'http://supabase-not-configured.local',
  anonKey || 'anon-key-not-set',
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storageKey: 'nexus.supabase.auth',
    },
  }
);

/**
 * The current Supabase access token, or null when signed out. supabase-js
 * keeps the session refreshed, so this returns a valid (non-expired) token
 * whenever a session exists. Used by the axios interceptors to authorize
 * requests.
 */
export async function getAccessToken() {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || null;
}

export default supabase;
