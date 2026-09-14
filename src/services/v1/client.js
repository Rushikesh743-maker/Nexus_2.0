/**
 * Centralized HTTP client for the platform API (/api/v1).
 *
 * One axios instance for the whole v1 surface:
 *  - attaches the Supabase access token on every request;
 *  - on a 401, retries once with a freshly read (auto-refreshed) token, and if
 *    that still fails, signs out and redirects to /login;
 *  - normalizes transport failures so UI code can distinguish "backend not
 *    running" from "not allowed" from "validation".
 *
 * The client holds no business logic and no mock data — the case area is
 * live-backed by design, exactly like the analysis section.
 */
import axios from 'axios';
import { getAccessToken } from '@/lib/supabase';

export const V1_BASE_URL = '/api/v1';

export class V1Error extends Error {
  constructor(message, { status = 0, code, offline = false, unauthenticated = false } = {}) {
    super(message);
    this.name = 'V1Error';
    this.status = status;
    this.code = code;
    this.offline = offline;
    this.unauthenticated = unauthenticated;
  }
}

/**
 * Normalize any axios failure into a V1Error.
 *
 * "Offline" means the platform backend is not reachable: no HTTP response at
 * all, or a 502/503/504 gateway error (what the Vite dev proxy returns when
 * the backend is down). UI code uses that flag to show the honest
 * "start the backend" state.
 */
function toV1Error(error) {
  if (axios.isAxiosError?.(error)) {
    const status = error.response?.status;
    const body = error.response?.data?.error;

    // A structured platform error — report its message verbatim.
    if (body) {
      return new V1Error(body.message || 'Request failed.', {
        status,
        code: body.code,
        unauthenticated: status === 401 || status === 403,
      });
    }

    // No response, or an unstructured 5xx: the platform backend itself is
    // not serving this request. (The Vite dev proxy answers 500 with an empty
    // body when the backend is down; a crashed backend answers 500 with
    // plain text. Both are infrastructure failures, not API rejections.)
    if (status == null || (status >= 500 && !error.response.data?.detail)) {
      return new V1Error(
        'The platform backend is not reachable. Start the backend (python3 backend/run.py) and reload.',
        { status: status || 0, offline: true }
      );
    }
    return new V1Error(error.message || 'Request failed.', { status });
  }
  return new V1Error(error?.message || 'Unexpected error.', { status: error?.status });
}

const client = axios.create({ baseURL: V1_BASE_URL, timeout: 20000 });

client.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  console.log('Supabase session exists:', !!token);
  console.log('Access token exists:', !!token);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  console.log('Authorization header attached:', !!config.headers?.Authorization);
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error?.config;
    const status = error?.response?.status;

    // A 401: the token may have expired. Re-read the (auto-refreshed) Supabase
    // token and retry the original request once.
    if (status === 401 && original && !original._retried) {
      original._retried = true;
      const token = await getAccessToken();
      if (token) {
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` };
        return client(original);
      }
    }

    // Still unauthenticated after retry: redirect to /login if needed without destroying Supabase session.
    if (status === 401) {
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.assign('/login');
      }
    }

    return Promise.reject(toV1Error(error));
  }
);

/** Run a request and return the data, with normalized errors. */
export async function request(method, url, body, config = {}) {
  const response = await client.request({ method, url, data: body, ...config });
  return response.data;
}

export { client };
export default client;
