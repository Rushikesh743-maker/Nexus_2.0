/**
 * Mappings between the platform API's v1 vocabulary and the existing
 * visualization constants (ENTITY_TYPES / RELATIONSHIP_TYPES).
 *
 * The API owns the canonical names; these maps only pick the closest existing
 * visual treatment so the graph renders with the established palette.
 */

export const V1_ENTITY_TYPE_KEYS = {
  person: 'person',
  organization: 'organization',
  vehicle: 'vehicle',
  location: 'address',
  phone: 'phone_number',
  account: 'bank_account',
  case_reference: 'asset',
  other: 'asset',
};

export const V1_RELATIONSHIP_CATEGORY = {
  ASSOCIATED_WITH: 'associate',
  CONNECTED_TO: 'hierarchical',
  OWNS: 'hierarchical',
  USED: 'used',
  CALLED: 'communication',
  LOCATED_AT: 'co_located',
  TRANSFERRED_TO: 'financial',
  MENTIONED_IN: 'mentioned_in',
};

/** v1 entity row -> node shape expected by NetworkGraph/EntityNode. */
export function toGraphNode(entity, degree = 0) {
  return {
    id: entity.id,
    name: entity.canonical_name,
    type: V1_ENTITY_TYPE_KEYS[entity.type] || 'asset',
    resolution: 'unverified',
    connections: degree,
    apiType: entity.type,
    aliases: entity.aliases || [],
  };
}

/** v1 relationship row -> edge shape expected by NetworkGraph. */
export function toGraphEdge(rel) {
  return {
    id: rel.id,
    sourceId: rel.source_entity_id,
    targetId: rel.target_entity_id,
    type: V1_RELATIONSHIP_CATEGORY[rel.relationship_type] || 'associate',
    label: rel.relationship_type,
    confidence: rel.confidence,
    metadata: rel.metadata,
  };
}

/** Case status -> badge tone. */
export const CASE_STATUS_TONE = {
  ACTIVE: 'info',
  OPEN: 'teal',
  ON_HOLD: 'warning',
  CLOSED: 'neutral',
  ARCHIVED: 'neutral',
  INVESTIGATING: 'info',
};

export const CASE_PRIORITY_TONE = {
  CRITICAL: 'danger',
  HIGH: 'warning',
  MEDIUM: 'info',
  LOW: 'neutral',
};
