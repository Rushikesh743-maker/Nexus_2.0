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
  active: { label: 'Active', variant: 'success', color: '#0d9488' },
  pending_review: { label: 'Under review', variant: 'warning', color: '#d97706' },
  closed: { label: 'Closed', variant: 'neutral', color: '#94a3b8' },
  archived: { label: 'Archived', variant: 'neutral', color: '#cbd5e1' },
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
  critical: { label: 'Critical', variant: 'danger', color: '#dc2626' },
  high: { label: 'High', variant: 'warning', color: '#d97706' },
  medium: { label: 'Medium', variant: 'info', color: '#0284c7' },
  low: { label: 'Low', variant: 'neutral', color: '#64748b' },
};

/* ---------------- Entities ---------------- */

export const ENTITY_TYPES = {
  person: { label: 'Person', icon: User, color: '#0d9488' },
  organization: { label: 'Organization', icon: Building2, color: '#6366f1' },
  phone_number: { label: 'Phone number', icon: Phone, color: '#0284c7' },
  bank_account: { label: 'Bank account', icon: Landmark, color: '#7c3aed' },
  vehicle: { label: 'Vehicle', icon: Car, color: '#d97706' },
  address: { label: 'Address', icon: MapPin, color: '#e11d48' },
  asset: { label: 'Asset', icon: Package, color: '#64748b' },
};

/**
 * Identity-resolution status — the outcome of automated identity matching
 * (mock presentation until the backend resolution service exists).
 * Deliberately neutral: NEXUS never labels a person; it tracks matches.
 */
export const ENTITY_RESOLUTION = {
  verified: { label: 'Verified', variant: 'success', color: '#0d9488' },
  possible_match: { label: 'Possible match', variant: 'warning', color: '#d97706' },
  unverified: { label: 'Unverified', variant: 'neutral', color: '#94a3b8' },
};

/* ---------------- Relationships ---------------- */

export const RELATIONSHIP_TYPES = {
  communication: { label: 'Communicated With', color: '#0ea5e9' },
  associate: { label: 'Associated With', color: '#14b8a6' },
  financial: { label: 'Transferred', color: '#8b5cf6' },
  co_located: { label: 'Visited', color: '#ec4899' },
  hierarchical: { label: 'Connected To', color: '#334e68' },
  family: { label: 'Associated With', color: '#f59e0b' },
  used: { label: 'Used', color: '#d97706' },
  mentioned_in: { label: 'Mentioned In', color: '#94a3b8' },
};

/* ---------------- Evidence ---------------- */

export const EVIDENCE_TYPES = {
  document: { label: 'Document', icon: FileText, color: '#334e68' },
  image: { label: 'Image', icon: Image, color: '#0d9488' },
  video: { label: 'Video', icon: Video, color: '#6366f1' },
  audio: { label: 'Audio', icon: Volume2, color: '#0284c7' },
  call_record: { label: 'Call record', icon: PhoneCall, color: '#7c3aed' },
  digital: { label: 'Digital', icon: HardDrive, color: '#0f766e' },
  forensic: { label: 'Forensic', icon: Fingerprint, color: '#e11d48' },
  financial_record: { label: 'Financial record', icon: IndianRupee, color: '#7c3aed' },
  physical: { label: 'Physical', icon: Package, color: '#64748b' },
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
  meeting: { label: 'Meeting', icon: Users, color: '#0d9488' },
  call: { label: 'Call', icon: PhoneCall, color: '#0284c7' },
  transaction: { label: 'Transaction', icon: IndianRupee, color: '#7c3aed' },
  travel: { label: 'Movement', icon: Truck, color: '#d97706' },
  surveillance: { label: 'Surveillance', icon: Eye, color: '#e11d48' },
  search: { label: 'Search', icon: Search, color: '#334e68' },
  incident: { label: 'Incident', icon: ShieldAlert, color: '#dc2626' },
  report: { label: 'Report', icon: FileText, color: '#64748b' },
};

/* ---------------- Locations ---------------- */

export const LOCATION_TYPES = {
  crime_scene: { label: 'Crime scene', color: '#e11d48' },
  surveillance: { label: 'Surveillance post', color: '#0d9488' },
  residence: { label: 'Residence', color: '#0284c7' },
  business: { label: 'Business', color: '#7c3aed' },
  transit: { label: 'Transit point', color: '#d97706' },
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
