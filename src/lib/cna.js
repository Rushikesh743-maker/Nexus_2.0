/**
 * Presentation metadata for the criminal-network-analysis backend.
 *
 * Mirrors the vocabularies the FastAPI service emits (entity types, edge
 * types, anomaly detectors, severities) so labels, colours and icons live in
 * one place — the same convention `lib/constants.js` uses for the mock data.
 *
 * Nothing here computes anything. Every number shown in the UI comes from the
 * backend, which carries its own sources and the rule that produced it.
 */
import {
  Users,
  MapPin,
  Building2,
  Car,
  FileText,
  Phone,
  Banknote,
  Eye,
  Share2,
  Radio,
  ShieldAlert,
  Repeat,
  Layers,
  Landmark,
  UserCheck,
  Network,
  Lock,
} from 'lucide-react';

/** Node types produced by `graph/build.py`. */
export const CNA_NODE_TYPES = {
  PERSON: { label: 'Person', icon: Users, tone: 'teal', color: 'var(--data-teal)', shape: 'circle' },
  ORG: { label: 'Organisation', icon: Building2, tone: 'violet', color: 'var(--data-violet)', shape: 'square' },
  LOCATION: { label: 'Location', icon: MapPin, tone: 'amber', color: 'var(--data-amber)', shape: 'diamond' },
  VEHICLE: { label: 'Vehicle', icon: Car, tone: 'sky', color: 'var(--data-sky)', shape: 'hexagon' },
  CASE: { label: 'Case record', icon: FileText, tone: 'navy', color: 'var(--ink-600)', shape: 'triangle' },
};

export function cnaNodeType(type) {
  return CNA_NODE_TYPES[type] || { label: type || 'Unknown', icon: Network, tone: 'navy', color: 'var(--data-neutral)', shape: 'circle' };
}

/** Edge vocabulary emitted by the graph builder. */
export const CNA_EDGE_TYPES = {
  CALLED: { label: 'Called', color: 'var(--data-teal)' },
  TRANSACTED_WITH: { label: 'Transacted with', color: 'var(--data-violet)' },
  SEEN_AT: { label: 'Seen at', color: 'var(--data-amber)' },
  CO_NAMED_IN: { label: 'Co-named in', color: 'var(--data-neutral)' },
  NAMED_IN: { label: 'Named in', color: 'var(--ink-400)' },
  REPORTS_TO: { label: 'Reports to', color: 'var(--data-rose)' },
  INSTRUCTED_BY: { label: 'Instructed by', color: 'var(--data-rose)' },
  SUPPLIED_BY: { label: 'Supplied by', color: 'var(--data-sky)' },
  USED_VEHICLE: { label: 'Used vehicle', color: 'var(--data-sky)' },
  LINKED_TO_ORG: { label: 'Linked to organisation', color: 'var(--data-violet)' },
  DIRECTOR_OF: { label: 'Director of', color: 'var(--data-violet)' },
};

export function cnaEdgeLabel(type) {
  return CNA_EDGE_TYPES[type]?.label || String(type || '').toLowerCase().replace(/_/g, ' ');
}

export function cnaEdgeColor(types = []) {
  for (const t of types) if (CNA_EDGE_TYPES[t]) return CNA_EDGE_TYPES[t].color;
  return 'var(--ink-400)';
}

/**
 * The nine suspicious-pattern detectors in `graph/anomaly.py`.
 * `question` states what the rule is actually asking — the detector explains
 * itself rather than presenting a bare score.
 */
export const CNA_FINDING_TYPES = {
  communication_burst: {
    label: 'Call-volume burst',
    icon: Radio,
    question: 'Did contact between subjects spike far above their own baseline on one day?',
  },
  burner_handset: {
    label: 'Burner handset',
    icon: Phone,
    question: 'Did a handset contact very few numbers over a short window and then fall silent?',
  },
  circular_fund_flow: {
    label: 'Circular fund flow',
    icon: Repeat,
    question: 'Did money leave an account and return to it through a chain of intermediaries?',
  },
  structuring: {
    label: 'Structuring',
    icon: Banknote,
    question: 'Were transfers repeatedly sized just below the reporting threshold?',
  },
  insulated_actor: {
    label: 'Insulated actor',
    icon: ShieldAlert,
    question: 'Is a subject ranked highly by position rather than by contact count?',
  },
  clean_skin_bridge: {
    label: 'Clean-skin bridge',
    icon: UserCheck,
    question:
      'Does someone with a checked record and no prior cases connect subjects who do have records?',
  },
  cross_community_broker: {
    label: 'Cross-group broker',
    icon: Share2,
    question: 'Does a subject hold links across several otherwise separate sub-groups?',
  },
  repeated_co_location: {
    label: 'Repeated co-location',
    icon: MapPin,
    question: 'Are two subjects repeatedly present together while never calling each other?',
  },
  custody_conflict: {
    label: 'Custody conflict',
    icon: Lock,
    question: 'Was a handset active while its registered user was recorded in judicial custody?',
  },
};

export function cnaFindingType(type) {
  return (
    CNA_FINDING_TYPES[type] || {
      label: String(type || '').replace(/_/g, ' '),
      icon: ShieldAlert,
      question: null,
    }
  );
}

/** Severity → Badge variant, matching the semantic states of the design system. */
export const CNA_SEVERITY = {
  high: { label: 'High', variant: 'danger' },
  medium: { label: 'Medium', variant: 'warning' },
  low: { label: 'Low', variant: 'info' },
};

export function cnaSeverity(sev) {
  return CNA_SEVERITY[sev] || { label: sev || 'Unrated', variant: 'neutral' };
}

/** Source systems the pipeline ingests. */
export const CNA_SOURCE_TYPES = {
  fir: { label: 'FIR', icon: FileText, tone: 'navy' },
  cdr: { label: 'Call records', icon: Phone, tone: 'teal' },
  transaction: { label: 'Financial', icon: Banknote, tone: 'violet' },
  surveillance: { label: 'Surveillance', icon: Eye, tone: 'amber' },
  social_media: { label: 'Social media', icon: Share2, tone: 'sky' },
  criminal_record: { label: 'Criminal history', icon: Landmark, tone: 'rose' },
  scanned: { label: 'Scanned FIR', icon: Layers, tone: 'navy' },
};

export function cnaSourceType(key) {
  return CNA_SOURCE_TYPES[key] || { label: String(key || '').replace(/_/g, ' '), icon: FileText, tone: 'navy' };
}

/** The six additive components of the influence model, in scoring order. */
export const CNA_INFLUENCE_COMPONENTS = [
  { key: 'betweenness', label: 'Betweenness', hint: 'Sits on the shortest routes between other members.' },
  { key: 'pagerank', label: 'PageRank', hint: 'Referenced by other members who are themselves significant.' },
  { key: 'degree', label: 'Degree', hint: 'Weighted count of direct connections.' },
  { key: 'eigenvector', label: 'Eigenvector', hint: 'Connected to well-connected members.' },
  { key: 'prior_record', label: 'Prior record', hint: 'Cases already on record for this subject.' },
  { key: 'bridging', label: 'Bridging', hint: 'Holds links that cross sub-group boundaries.' },
];

/**
 * The disclosure shown wherever backend analysis is presented. The reference
 * system is explicit that it is an investigative aid, not evidence.
 */
export const CNA_DISCLOSURE =
  'Analytical assistance only. Every finding states the rule that produced it and the source records behind it. ' +
  'This is an investigative aid, not evidence, and it does not determine guilt.';

/** All data in the corpus is synthetic — stated wherever the corpus is shown. */
export const CNA_SYNTHETIC_NOTICE =
  'All records in this case are synthetic and generated by data/generator.py. No real case material is used.';

export function formatScore(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Number(value).toFixed(digits);
}

export function formatPercent(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

/** Indian-format currency used by the transaction views. */
export function formatINR(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
}
