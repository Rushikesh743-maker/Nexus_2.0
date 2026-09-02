import axios from 'axios';
import { storage } from '@/lib/storage';

/**
 * Shared API plumbing.
 *
 * Every service function is written against this module:
 *  - in mock mode (default) it resolves local mock data after simulated latency;
 *  - in API mode it would call `api` (Axios) with the same return shapes.
 *
 * Swap strategy: set VITE_USE_MOCK_API=false and VITE_API_BASE_URL — no UI changes.
 */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
export const USE_MOCK_API = (import.meta.env.VITE_USE_MOCK_API ?? 'true') !== 'false';

const SESSION_KEY = 'nexus.session';

export function getStoredSession() {
  try {
    return JSON.parse(storage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

export function storeSession(session) {
  if (session) storage.setItem(SESSION_KEY, JSON.stringify(session));
  else storage.removeItem(SESSION_KEY);
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const session = getStoredSession();
  if (session?.token) {
    config.headers.Authorization = `Bearer ${session.token}`;
  }
  return config;
});

/** Normalise transport errors into a predictable `{ status, message }` object. */
export function normalizeError(error) {
  if (axios.isAxiosError?.(error)) {
    const status = error.response?.status;
    const err = new Error(error.response?.data?.message || error.message || 'Request failed.');
    err.status = status;
    err.isAuthError = status === 401 || status === 403;
    return err;
  }
  const err = error instanceof Error ? error : new Error('Unexpected error.');
  err.status = error?.status;
  err.isAuthError = error?.isAuthError ?? false;
  return err;
}

api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(normalizeError(error))
);

/** Simulated network latency for the mock layer. */
export function mockLatency(ms = 240 + Math.random() * 260) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Deep-copy mock records so UI state can never mutate the mock store. */
export function clone(value) {
  if (typeof structuredClone === 'function') return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

export { api };
export default api;
