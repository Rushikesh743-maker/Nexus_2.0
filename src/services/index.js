/**
 * Service layer barrel. UI components import from here only — never from
 * `src/mock` directly.
 */
export { default as api, API_BASE_URL, USE_MOCK_API } from './api';
export * as authService from './authService';
export * as investigationService from './investigationService';
export * as evidenceService from './evidenceService';
export * as intelligenceService from './intelligenceService';
export * as analysisService from './analysisService';
export * as cnaService from './cnaService';
