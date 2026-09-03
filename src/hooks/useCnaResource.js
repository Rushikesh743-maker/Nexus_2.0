import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Load one resource from the analysis backend.
 *
 * The analysis screens have no mock fallback by design, so this hook keeps the
 * three states the UI must tell apart: loading, an error that explains itself
 * (offline / forbidden / missing capability), and data.
 *
 * @param {Function} loader  called with no arguments; must return a promise
 * @param {Array}    deps    re-run when these change
 * @param {{enabled?: boolean}} options
 */
export function useCnaResource(loader, deps = [], { enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(enabled);

  // Guards against a slow response from a superseded request overwriting a
  // newer one, and against setting state after unmount.
  const requestId = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(() => {
    if (!enabled) {
      setLoading(false);
      return Promise.resolve(null);
    }
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    return loader()
      .then((result) => {
        if (!mounted.current || id !== requestId.current) return null;
        setData(result);
        setLoading(false);
        return result;
      })
      .catch((e) => {
        if (!mounted.current || id !== requestId.current) return null;
        setError(e);
        setLoading(false);
        return null;
      });
    // `loader` is intentionally not a dependency: callers pass an inline
    // arrow, and `deps` is the explicit re-run contract.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    run();
  }, [run]);

  return { data, error, loading, reload: run, setData };
}
