import {
  User,
  Building2,
  Phone,
  Landmark,
  Car,
  MapPin,
  Package,
  FileText,
  Image,
  Video,
  Volume2,
  PhoneCall,
  HardDrive,
  Fingerprint,
  IndianRupee,
  Users,
  Truck,
  Eye,
  Search,
  ShieldAlert,
  TrendingUp,
  Share2,
  Clock,
  AlertTriangle,
} from 'lucide-react';

export const APP_NAME = 'NEXUS';
export const APP_VERSION = '0.1.0';
export const APP_TAGLINE = 'Investigation Intelligence Platform';

/* ---------------- Investigations ---------------- */

export const INVESTIGATION_STATUS = {
  active: { label: 'Active', variant: 'success', color: 'var(--data-teal)' },
  pending_review: { label: 'Under review', variant: 'warning', color: 'var(--data-amber)' },
  closed: { label: 'Closed', variant: 'neutral', color: 'var(--ink-400)' },
  archived: { label: 'Archived', variant: 'neutral', color: 'var(--ink-300)' },
};

export const CASE_TYPES = {
  /* Canonical case types (Prompt 3 spec) */
  missing_person: { label: 'Missing Person' },
  kidnapping: { label: 'Kidnapping' },
  fraud: { label: 'Fraud' },
  financial_crime: { label: 'Financial Crime' },
  cyber_crime: { label: 'Cyber Crime' },
  theft: { label: 'Theft' },
  other: { label: 'Other' },
  /* Legacy labels for pre-existing fictional cases */
  financial: { label: 'Financial Crime' },
  cyber: { label: 'Cyber Crime' },
  betting: { label: 'Betting & gambling' },
  narcotics: { label: 'Narcotics' },
  counterfeiting: { label: 'Counterfeiting' },
  smuggling: { label: 'Smuggling' },
  extortion: { label: 'Extortion' },
  organised_network: { label: 'Organised Network' },
};

/** Ordered options for the create-investigation form. */
export const CASE_TYPE_OPTIONS = [
  { value: 'missing_person', label: 'Missing Person' },
  { value: 'kidnapping', label: 'Kidnapping' },
  { value: 'fraud', label: 'Fraud' },
  { value: 'financial_crime', label: 'Financial Crime' },
  { value: 'cyber_crime', label: 'Cyber Crime' },
  { value: 'theft', label: 'Theft' },
  { value: 'other', label: 'Other' },
];

export function caseTypeLabel(key) {
  return CASE_TYPES[key]?.label || key || '—';
}

/* ---------------- Dashboard activity feed (UI mock events) ---------------- */

export const ACTIVITY_TYPES = {
  evidence_added: { label: 'Evidence', icon: 'Upload' },
  entity_match: { label: 'Entity match', icon: 'UserSearch' },
  relationship_detected: { label: 'Relationship', icon: 'Share2' },
  timeline_updated: { label: 'Timeline', icon: 'History' },
  report_generated: { label: 'Report', icon: 'FileText' },
};

export const PRIORITY = {
  critical: { label: 'Critical', variant: 'danger', color: 'var(--data-rose)' },
  high: { label: 'High', variant: 'warning', color: 'var(--data-amber)' },
  medium: { label: 'Medium', variant: 'info', color: 'var(--data-sky)' },
  low: { label: 'Low', variant: 'neutral', color: 'var(--data-neutral)' },
};

/* ---------------- Entities ---------------- */

export const ENTITY_TYPES = {
  person: { label: 'Person', icon: User, color: 'var(--data-teal)' },
  organization: { label: 'Organization', icon: Building2, color: 'var(--data-violet)' },
  phone_number: { label: 'Phone number', icon: Phone, color: 'var(--data-sky)' },
  bank_account: { label: 'Bank account', icon: Landmark, color: 'var(--data-violet)' },
  vehicle: { label: 'Vehicle', icon: Car, color: 'var(--data-amber)' },
  address: { label: 'Address', icon: MapPin, color: 'var(--data-rose)' },
  asset: { label: 'Asset', icon: Package, color: 'var(--data-neutral)' },
};

/**
 * Identity-resolution status — the outcome of automated identity matching
 * (mock presentation until the backend resolution service exists).
 * Deliberately neutral: NEXUS never labels a person; it tracks matches.
 */
export const ENTITY_RESOLUTION = {
  verified: { label: 'Verified', variant: 'success', color: 'var(--data-teal)' },
  possible_match: { label: 'Possible match', variant: 'warning', color: 'var(--data-amber)' },
  unverified: { label: 'Unverified', variant: 'neutral', color: 'var(--ink-400)' },
};

/* ---------------- Relationships ---------------- */

export const RELATIONSHIP_TYPES = {
  communication: { label: 'Communicated With', color: 'var(--data-sky)' },
  associate: { label: 'Associated With', color: 'var(--data-teal)' },
  financial: { label: 'Transferred', color: 'var(--data-violet)' },
  co_located: { label: 'Visited', color: 'var(--data-rose)' },
  hierarchical: { label: 'Connected To', color: 'var(--ink-700)' },
  family: { label: 'Associated With', color: 'var(--data-amber)' },
  used: { label: 'Used', color: 'var(--data-amber)' },
  mentioned_in: { label: 'Mentioned In', color: 'var(--ink-400)' },
};

/* ---------------- Evidence ---------------- */

export const EVIDENCE_TYPES = {
  document: { label: 'Document', icon: FileText, color: 'var(--ink-700)' },
  image: { label: 'Image', icon: Image, color: 'var(--data-teal)' },
  video: { label: 'Video', icon: Video, color: 'var(--data-violet)' },
  audio: { label: 'Audio', icon: Volume2, color: 'var(--data-sky)' },
  call_record: { label: 'Call record', icon: PhoneCall, color: 'var(--data-violet)' },
  digital: { label: 'Digital', icon: HardDrive, color: 'var(--accent-strong)' },
  forensic: { label: 'Forensic', icon: Fingerprint, color: 'var(--data-rose)' },
  financial_record: { label: 'Financial record', icon: IndianRupee, color: 'var(--data-violet)' },
  physical: { label: 'Physical', icon: Package, color: 'var(--data-neutral)' },
};

/**
 * Uploadable evidence file formats. Lifecycle statuses a file moves through
 * after upload: uploaded → processing → processed | needs_review | failed.
 */
export const FILE_TYPES = {
  pdf: { label: 'PDF' },
  docx: { label: 'DOCX' },
  txt: { label: 'TXT' },
  csv: { label: 'CSV' },
  xlsx: { label: 'XLSX' },
  json: { label: 'JSON' },
  jpg: { label: 'JPG' },
  png: { label: 'PNG' },
};

export const ACCEPTED_EXTENSIONS = Object.keys(FILE_TYPES);

export const EVIDENCE_STATUS = {
  uploaded: { label: 'Uploaded', variant: 'neutral' },
  processing: { label: 'Processing', variant: 'info' },
  processed: { label: 'Processed', variant: 'success' },
  needs_review: { label: 'Needs review', variant: 'warning' },
  failed: { label: 'Failed', variant: 'danger' },
  archived: { label: 'Archived', variant: 'neutral' },
};

/* ---------------- Events ---------------- */

export const EVENT_TYPES = {
  meeting: { label: 'Meeting', icon: Users, color: 'var(--data-teal)' },
  call: { label: 'Call', icon: PhoneCall, color: 'var(--data-sky)' },
  transaction: { label: 'Transaction', icon: IndianRupee, color: 'var(--data-violet)' },
  travel: { label: 'Movement', icon: Truck, color: 'var(--data-amber)' },
  surveillance: { label: 'Surveillance', icon: Eye, color: 'var(--data-rose)' },
  search: { label: 'Search', icon: Search, color: 'var(--ink-700)' },
  incident: { label: 'Incident', icon: ShieldAlert, color: 'var(--data-rose)' },
  report: { label: 'Report', icon: FileText, color: 'var(--data-neutral)' },
};

/* ---------------- Locations ---------------- */

export const LOCATION_TYPES = {
  crime_scene: { label: 'Crime scene', color: 'var(--data-rose)' },
  surveillance: { label: 'Surveillance post', color: 'var(--data-teal)' },
  residence: { label: 'Residence', color: 'var(--data-sky)' },
  business: { label: 'Business', color: 'var(--data-violet)' },
  transit: { label: 'Transit point', color: 'var(--data-amber)' },
};

/* ---------------- Intelligence insights ---------------- */

export const INSIGHT_CATEGORIES = {
  pattern: { label: 'Pattern', icon: TrendingUp, variant: 'teal' },
  link: { label: 'Link', icon: Share2, variant: 'info' },
  geo: { label: 'Geospatial', icon: MapPin, variant: 'warning' },
  temporal: { label: 'Temporal', icon: Clock, variant: 'neutral' },
  anomaly: { label: 'Anomaly', icon: AlertTriangle, variant: 'danger' },
};

export const INSIGHT_STATUS = {
  new: { label: 'New', variant: 'warning' },
  reviewed: { label: 'Reviewed', variant: 'info' },
  verified: { label: 'Verified', variant: 'success' },
};

/* ---------------- Reports ---------------- */

export const REPORT_TYPES = {
  case_summary: { label: 'Case summary' },
  evidence_index: { label: 'Evidence index' },
  network_analysis: { label: 'Network analysis' },
  timeline_digest: { label: 'Timeline digest' },
};

export const REPORT_STATUS = {
  queued: { label: 'Queued', variant: 'warning' },
  ready: { label: 'Ready', variant: 'success' },
  failed: { label: 'Failed', variant: 'danger' },
};

/* ---------------- Shared helpers ---------------- */

export function confidenceVariant(value = 0) {
  if (value >= 80) return 'success';
  if (value >= 60) return 'info';
  return 'warning';
}

export function confidenceLabel(value = 0) {
  if (value >= 80) return 'High confidence';
  if (value >= 60) return 'Moderate confidence';
  return 'Low confidence';
}
