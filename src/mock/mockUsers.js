/**
 * Mock personnel directory.
 * ─────────────────────────────────────────────────────────────────────────
 * DEVELOPMENT AUTHENTICATION ONLY.
 *
 * These records exist purely for the frontend demo (the mock branch of
 * `services/authService.js`). Production authentication MUST be served by
 * the backend identity service (set VITE_USE_MOCK_API=false) — never ship
 * these accounts or credentials in a real deployment. The login screen
 * surfaces the development account only while mock mode is active.
 * ─────────────────────────────────────────────────────────────────────────
 */

/** Shared demo password for the mock accounts below. */
export const DEMO_PASSWORD = 'nexus2026';

/**
 * Primary development account for the frontend build.
 * Clearly separated from the fictional personnel directory and from
 * production authentication (which is a backend concern).
 */
export const DEMO_DEV_ACCOUNT = {
  id: 'usr-demo',
  name: 'Demo Investigator',
  rank: '',
  role: 'Development account',
  unit: 'NEXUS demo workspace',
  email: 'demo-investigator@nexus.local',
  password: DEMO_PASSWORD,
};

/** Fictional personnel — also used as case leads and team members. */
export const mockUsers = [
  DEMO_DEV_ACCOUNT,
  {
    id: 'usr-001',
    name: 'Priya Deshmukh',
    rank: 'Inspector',
    role: 'Lead Investigator',
    unit: 'Cyber Crime Unit, Pune',
    email: 'priya.deshmukh@nexus.gov.in',
    password: DEMO_PASSWORD,
  },
  {
    id: 'usr-002',
    name: 'Arjun Patil',
    rank: 'Sub-Inspector',
    role: 'Field Investigator',
    unit: 'Crime Branch, Pune',
    email: 'arjun.patil@nexus.gov.in',
    password: DEMO_PASSWORD,
  },
  {
    id: 'usr-003',
    name: 'Sneha Joshi',
    rank: 'Inspector',
    role: 'Intelligence Analyst',
    unit: 'State Intelligence Department',
    email: 'sneha.joshi@nexus.gov.in',
    password: DEMO_PASSWORD,
  },
  {
    id: 'usr-004',
    name: 'Vikas Rane',
    rank: 'Assistant Commissioner',
    role: 'Reviewing Officer',
    unit: 'Commissionerate, Mumbai',
    email: 'vikas.rane@nexus.gov.in',
    password: DEMO_PASSWORD,
  },
];

export default mockUsers;
