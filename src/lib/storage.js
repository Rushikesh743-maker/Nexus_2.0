/**
 * Safe localStorage wrapper.
 *
 * Sandboxed preview frames (opaque origins) and some privacy modes throw on
 * localStorage access. We probe once and fall back to an in-memory store so
 * the app degrades gracefully (persistence simply lasts for the session).
 */
function resolveStorage() {
  try {
    const probeKey = '__nexus_probe__';
    window.localStorage.setItem(probeKey, '1');
    window.localStorage.removeItem(probeKey);
    return window.localStorage;
  } catch {
    const memory = new Map();
    return {
      getItem: (key) => (memory.has(key) ? memory.get(key) : null),
      setItem: (key, value) => {
        memory.set(key, String(value));
      },
      removeItem: (key) => {
        memory.delete(key);
      },
    };
  }
}

export const storage = resolveStorage();
