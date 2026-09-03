import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { storage } from '@/lib/storage';

const ThemeContext = createContext(null);

const KEY = 'nexus.theme';
export const THEMES = ['light', 'dark', 'system'];

/** What `system` currently resolves to. */
function systemTheme() {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function storedPreference() {
  const value = storage.getItem(KEY);
  return THEMES.includes(value) ? value : 'system';
}

/** Stamp the resolved theme on <html> so the CSS variables switch. */
function apply(resolved) {
  const root = document.documentElement;
  root.setAttribute('data-theme', resolved);
  root.style.colorScheme = resolved;
}

/**
 * Theme provider.
 *
 * `preference` is what the analyst chose (light / dark / system); `theme` is
 * what that resolves to right now. Keeping them separate means "system" keeps
 * following the OS after a reload instead of being frozen at its first value.
 */
export function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(storedPreference);
  const [resolved, setResolved] = useState(() =>
    storedPreference() === 'system' ? systemTheme() : storedPreference()
  );

  // Follow the OS while the preference is "system".
  useEffect(() => {
    if (preference !== 'system') {
      setResolved(preference);
      return undefined;
    }
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mq) {
      setResolved('light');
      return undefined;
    }
    const sync = () => setResolved(mq.matches ? 'dark' : 'light');
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, [preference]);

  useEffect(() => {
    apply(resolved);
  }, [resolved]);

  const setTheme = useCallback((next) => {
    if (!THEMES.includes(next)) return;
    setPreference(next);
    storage.setItem(KEY, next);
  }, []);

  /** Flip to the opposite of what is on screen, and pin it. */
  const toggle = useCallback(() => {
    setTheme(resolved === 'dark' ? 'light' : 'dark');
  }, [resolved, setTheme]);

  const value = useMemo(
    () => ({ theme: resolved, preference, setTheme, toggle, isDark: resolved === 'dark' }),
    [resolved, preference, setTheme, toggle]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider');
  return ctx;
}

/**
 * Read a themed CSS variable as a real colour string.
 *
 * Canvas and some SVG consumers cannot resolve `var(--x)`, so charts and the
 * graph read their chrome colours through this instead of hardcoding hex.
 */
export function cssVar(name, fallback = '') {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name);
  return value.trim() || fallback;
}
