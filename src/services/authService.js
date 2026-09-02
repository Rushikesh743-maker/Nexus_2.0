import { USE_MOCK_API, api, mockLatency, clone, getStoredSession, storeSession } from './api';
import { mockUsers } from '@/mock/mockUsers';

/**
 * Authentication service. Mock mode validates against the demo user list;
 * API mode expects POST /auth/login and GET /auth/session.
 */

function publicUser(raw) {
  const { password, ...user } = raw;
  return user;
}

export function getDemoCredentials() {
  return { email: mockUsers[0].email, password: mockUsers[0].password };
}

async function mockLogin({ email, password }) {
  await mockLatency(480);
  const user = mockUsers.find((u) => u.email.toLowerCase() === String(email).trim().toLowerCase());
  if (!user || user.password !== password) {
    const err = new Error('Invalid email or password.');
    err.code = 'INVALID_CREDENTIALS';
    throw err;
  }
  const session = { token: `mock-jwt.${btoa(user.id)}`, user: publicUser(user) };
  storeSession(session);
  return clone(session);
}

export async function login({ email, password }) {
  if (!USE_MOCK_API) {
    const { data } = await api.post('/auth/login', { email, password });
    storeSession(data);
    return data;
  }
  return mockLogin({ email, password });
}

export async function getSession() {
  if (!USE_MOCK_API) {
    try {
      const { data } = await api.get('/auth/session');
      storeSession(data);
      return data.user;
    } catch {
      storeSession(null);
      return null;
    }
  }
  const stored = getStoredSession();
  if (!stored?.token) return null;
  const user = mockUsers.find((u) => u.id === stored.user?.id);
  if (!user) return null;
  return publicUser(user);
}

export async function logout() {
  if (!USE_MOCK_API) {
    try {
      await api.post('/auth/logout');
    } catch {
      /* session cleared locally regardless */
    }
  }
  storeSession(null);
}
