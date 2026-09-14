/**
 * Frontend auth-flow regression test.
 *
 * Exercises the REAL service layer (authService + v1 client) against the
 * Vite dev server proxy (http://127.0.0.1:5173), and adapts to the backend
 * state it finds:
 *
 *   backend UP    → JWT login, normalized session, /auth/me, live case data,
 *                   wrong password rejected with 401 (no mock fallback).
 *   backend DOWN  → offline classification (proxy 500 / no response),
 *                   graceful fallback to the offline demo session, wrong
 *                   password still rejected.
 *
 * Prerequisites: `npm run dev` running on :5173 (the backend may be up or
 * down). Run: npm run test:frontend-auth
 */
import { createServer } from 'vite';

const PROXY = 'http://127.0.0.1:5173/api/v1';
const DEMO = { email: 'demo-investigator@nexus.local', password: 'nexus2026' };

const SERVER = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
});
const load = (p) => SERVER.ssrLoadModule(p);

const { client } = await load('/src/services/v1/client.js');
client.defaults.baseURL = PROXY;
const authService = await load('/src/services/authService.js');
const v1Auth = await load('/src/services/v1/authService.js');
const caseService = (await load('/src/services/v1/caseService.js')).default;
const { V1Error } = await load('/src/services/v1/client.js');

let failures = 0;
function check(label, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures += 1;
}

// Which mode are we in?
let online = false;
try {
  online = (await client.get('/health')).data.status === 'ok';
} catch {
  online = false;
}
console.log(`backend ${online ? 'UP (JWT path)' : 'DOWN (offline path)'}\n`);

if (online) {
  // 1) Direct JWT login against the backend
  const jwt = await v1Auth.login(DEMO.email, DEMO.password);
  check('JWT login returns a signed token', jwt.access_token?.startsWith('eyJ'), jwt.user?.role);
  check('JWT login returns the user', jwt.user?.email === DEMO.email);

  // 2) Platform login normalizes to the session shape the client uses
  const session = await authService.login({ email: DEMO.email, password: DEMO.password });
  check('session normalized ({token, user})', Boolean(session.token) && session.token.startsWith('eyJ'));
  check('not flagged offline', !authService.isOfflineSession());

  // 3) Session restore verifies the JWT through /auth/me
  const me = await authService.getSession();
  check('getSession verifies JWT', me?.name === 'Demo Investigator' && me?.role === 'INVESTIGATOR');

  // 4) Case data flows with the JWT header attached by the interceptor
  const cases = await caseService.listCases();
  check('caseService.listCases with JWT', Array.isArray(cases) && cases.length >= 4, `${cases.length} cases`);
  const detail = await caseService.getCase(cases[0].id);
  check('case detail payload', detail.case_number?.startsWith('CASE-') && detail.counts.entities > 0);

  // 5) Wrong password is a real 401 — never silently demoted to mock login
  let rejected = null;
  try {
    await authService.login({ email: DEMO.email, password: 'definitely-wrong' });
  } catch (e) {
    rejected = e;
  }
  check('wrong password rejected (no mock fallback)', rejected?.status === 401, rejected?.message);
} else {
  // 1) The v1 layer reports an offline error (proxy 500 / no response)
  let offlineError = null;
  try {
    await v1Auth.login(DEMO.email, DEMO.password);
  } catch (e) {
    offlineError = e;
  }
  check('v1 error classified offline', offlineError instanceof V1Error && offlineError.offline, `status=${offlineError?.status}`);

  // 2) Platform login falls back to the offline demo session
  const session = await authService.login({ email: DEMO.email, password: DEMO.password });
  check('offline fallback session', session.token?.startsWith('mock-jwt.') === true);
  check('flagged as offline', authService.isOfflineSession());

  // 3) Offline session restores without a backend
  const restored = await authService.getSession();
  check('offline session restore', restored?.name === 'Demo Investigator');

  // 4) Wrong password still rejected
  let rejected = null;
  try {
    await authService.login({ email: DEMO.email, password: 'definitely-wrong' });
  } catch (e) {
    rejected = e;
  }
  check('wrong password rejected offline', rejected?.code === 'INVALID_CREDENTIALS');
}

await SERVER.close();
if (failures) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAuth flow test passed.');
