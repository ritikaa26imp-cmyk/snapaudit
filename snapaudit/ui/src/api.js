import axios from 'axios';

/** Base URL for the FastAPI backend (see root `main.py` / uvicorn). */
const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
});

/**
 * @typedef {Object} ComparePayload
 * @property {string} session_id
 * @property {string} comparison_type
 * @property {string} [category_hint]
 * @property {string[]} image_set_1
 * @property {string[]} image_set_2
 * @property {string} [user_prompt]
 */

/**
 * Run the full comparison pipeline (Pass 1 + rollup + Pass 2).
 * @param {ComparePayload} payload
 */
export function compareImages(payload) {
  return api.post('/api/v1/compare', payload);
}

/**
 * Paginated audit list.
 * @param {Record<string, string|number|undefined|null>} filters
 */
export function getAudits(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  });
  const q = params.toString();
  return api.get(q ? `/api/v1/audits?${q}` : '/api/v1/audits');
}

/**
 * Single audit row (full JSON).
 * @param {string} auditId
 */
export function getAudit(auditId) {
  return api.get(`/api/v1/audits/${encodeURIComponent(auditId)}`);
}

/**
 * Download CSV matching the same filters as the list view (no pagination).
 * @param {Record<string, string|undefined|null>} filters
 */
export function exportAudits(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  });
  const q = params.toString();
  return api.get(q ? `/api/v1/audits/export?${q}` : '/api/v1/audits/export', {
    responseType: 'blob',
  });
}

/**
 * Pass 1 visibility on one image (data URL or http URL string).
 * @param {string} image
 */
export function checkVisibility(image) {
  return api.post('/api/v1/visibility', { image });
}

/** Health + active model from config. */
export function getHealth() {
  return api.get('/api/v1/health');
}

/** Parsed `policies/categories.yaml` for the Policy page. */
export function getPolicyCategories() {
  return api.get('/api/v1/policy/categories');
}

export default api;
