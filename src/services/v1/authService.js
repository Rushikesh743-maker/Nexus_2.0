/**
 * v1 authentication surface.
 *
 * There is no login endpoint — authentication is Supabase Auth (see
 * `services/authService.js`). The only NEXUS endpoint here is `GET /auth/me`,
 * which returns the NEXUS profile + role for the verified Supabase identity.
 * The request interceptor attaches the Supabase access token.
 */
import { request } from './client';

export function me() {
  return request('get', '/auth/me');
}

export default { me };
