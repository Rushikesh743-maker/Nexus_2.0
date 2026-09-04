/**
 * Offline place gazetteer.
 *
 * The map only ever plots coordinates it was given — there is no geocoding
 * service in this build. A document that carries explicit coordinates is used
 * as-is; otherwise a place name is matched against this table. Anything not
 * matched is still extracted as an address entity, it simply is not mapped.
 *
 * Coordinates are approximate locality centroids.
 */
export const GAZETTEER = [
  /* ---- Pune ---- */
  ['Pune', 18.5204, 73.8567],
  ['Pune Railway Station', 18.5286, 73.8743],
  ['Pune Camp', 18.5138, 73.8785],
  ['Shivajinagar', 18.5308, 73.8475],
  ['Shivajinagar Bus Stand', 18.5308, 73.8475],
  ['Kothrud', 18.5074, 73.8077],
  ['Karve Nagar', 18.4899, 73.8161],
  ['Deccan Gymkhana', 18.5169, 73.8404],
  ['Deccan', 18.5169, 73.8404],
  ['Swargate', 18.5011, 73.8586],
  ['Swargate Bus Depot', 18.5011, 73.8586],
  ['Hadapsar', 18.5089, 73.926],
  ['Kharadi', 18.5515, 73.9476],
  ['Viman Nagar', 18.5679, 73.9143],
  ['Koregaon Park', 18.5362, 73.8939],
  ['Aundh', 18.5593, 73.8078],
  ['Baner', 18.5642, 73.7769],
  ['Wakad', 18.5975, 73.7625],
  ['Hinjewadi', 18.5913, 73.7389],
  ['Pimpri', 18.6298, 73.7997],
  ['Chinchwad', 18.6431, 73.7929],
  ['Katraj', 18.4529, 73.8654],
  ['Warje', 18.4816, 73.8071],
  ['Sinhagad Road', 18.4747, 73.8261],
  ['Yerwada', 18.5511, 73.8797],
  ['Chakan', 18.7606, 73.8623],
  ['MIDC Chakan', 18.7606, 73.8623],
  ['Gultekdi', 18.4828, 73.8591],
  ['Market Yard', 18.4828, 73.8591],
  ['Lonavala', 18.7546, 73.4062],
  ['Talegaon', 18.7355, 73.6752],
  ['Dehu Road', 18.7108, 73.7414],
  ['Khadki', 18.5622, 73.8402],
  ['Bund Garden', 18.5362, 73.8776],
  ['FC Road', 18.5204, 73.8408],
  ['JM Road', 18.5236, 73.8437],
  ['Magarpatta', 18.5158, 73.9285],

  /* ---- Mumbai / MMR ---- */
  ['Mumbai', 19.076, 72.8777],
  ['Dadar', 19.018, 72.8435],
  ['Andheri', 19.1136, 72.8697],
  ['Andheri East', 19.1136, 72.8697],
  ['Bandra', 19.0596, 72.8295],
  ['Kurla', 19.0697, 72.8743],
  ['Borivali', 19.2307, 72.8567],
  ['Thane', 19.2183, 72.9781],
  ['Bhiwandi', 19.2967, 73.0631],
  ['Navi Mumbai', 19.033, 73.0297],
  ['Panvel', 18.9894, 73.1175],
  ['Kalyan', 19.2437, 73.1355],
  ['Vashi', 19.077, 72.9986],
  ['Chembur', 19.0522, 72.9005],
  ['Bandra Kurla Complex', 19.0669, 72.8687],
  ['Chhatrapati Shivaji Maharaj Terminus', 18.9401, 72.8353],
  ['CSMT', 18.9401, 72.8353],
  ['Lokmanya Tilak Terminus', 19.0679, 72.8996],

  /* ---- Rest of Maharashtra ---- */
  ['Nashik', 19.9975, 73.7898],
  ['Nagpur', 21.1458, 79.0882],
  ['Aurangabad', 19.8762, 75.3433],
  ['Chhatrapati Sambhajinagar', 19.8762, 75.3433],
  ['Kolhapur', 16.705, 74.2433],
  ['Solapur', 17.6599, 75.9064],
  ['Satara', 17.6805, 74.0183],
  ['Sangli', 16.8524, 74.5815],
  ['Ahmednagar', 19.0948, 74.748],
  ['Jalgaon', 21.0077, 75.5626],
  ['Latur', 18.4088, 76.5604],
  ['Ratnagiri', 16.9902, 73.312],
  ['Mahabaleshwar', 17.9307, 73.6477],
  ['Shirdi', 19.7645, 74.4762],
  ['Alandi', 18.6773, 73.8987],
  ['Baramati', 18.1514, 74.5815],

  /* ---- Other cities that show up in transit records ---- */
  ['Delhi', 28.6139, 77.209],
  ['Bengaluru', 12.9716, 77.5946],
  ['Bangalore', 12.9716, 77.5946],
  ['Hyderabad', 17.385, 78.4867],
  ['Ahmedabad', 23.0225, 72.5714],
  ['Surat', 21.1702, 72.8311],
  ['Indore', 22.7196, 75.8577],
  ['Goa', 15.2993, 74.124],
  ['Panaji', 15.4909, 73.8278],
  ['Belgaum', 15.8497, 74.4977],
  ['Hubli', 15.3647, 75.124],
];

/** Longest names first so "Pune Railway Station" wins over "Pune". */
const ORDERED = [...GAZETTEER].sort((a, b) => b[0].length - a[0].length);

/**
 * Best gazetteer match inside a free-text string.
 * Returns `{ name, lat, lng }` or null. Matching is whole-word and
 * case-insensitive so "kothrud" and "Kothrud," both resolve.
 */
export function resolvePlace(text) {
  if (!text) return null;
  const haystack = ` ${String(text).toLowerCase().replace(/[^a-z0-9]+/g, ' ')} `;
  for (const [name, lat, lng] of ORDERED) {
    const needle = ` ${name.toLowerCase().replace(/[^a-z0-9]+/g, ' ')} `;
    if (haystack.includes(needle)) return { name, lat, lng };
  }
  return null;
}

/** True when the phrase is a known place — used to keep places out of person names. */
export function isKnownPlace(phrase) {
  const norm = String(phrase || '').toLowerCase().trim();
  return GAZETTEER.some(([name]) => name.toLowerCase() === norm);
}
