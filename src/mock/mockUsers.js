/**
 * Mock personnel directory.
 * ─────────────────────────────────────────────────────────────────────────
 * Fictional staff used only as *data* by the standalone mock preview screens
 * (case leads, team members, "requested by"). These are not login accounts and
 * carry no credentials — authentication is Supabase Auth (see
 * `services/authService.js`), and the platform backend resolves the real
 * user. Never treat these records as identities.
 * ─────────────────────────────────────────────────────────────────────────
 */

/** Fictional personnel — used as case leads and team members in mock data. */
export const mockUsers = [
  {
    id: 'usr-001',
    name: 'Priya Deshmukh',
    rank: 'Inspector',
    role: 'Lead Investigator',
    unit: 'Cyber Crime Unit, Pune',
    email: 'priya.deshmukh@nexus.gov.in',
  },
  {
    id: 'usr-002',
    name: 'Arjun Patil',
    rank: 'Sub-Inspector',
    role: 'Field Investigator',
    unit: 'Crime Branch, Pune',
    email: 'arjun.patil@nexus.gov.in',
  },
  {
    id: 'usr-003',
    name: 'Sneha Joshi',
    rank: 'Inspector',
    role: 'Intelligence Analyst',
    unit: 'State Intelligence Department',
    email: 'sneha.joshi@nexus.gov.in',
  },
  {
    id: 'usr-004',
    name: 'Vikas Rane',
    rank: 'Assistant Commissioner',
    role: 'Reviewing Officer',
    unit: 'Commissionerate, Mumbai',
    email: 'vikas.rane@nexus.gov.in',
  },
];

export default mockUsers;
