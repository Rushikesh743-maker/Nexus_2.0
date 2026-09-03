import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { ToastViewport } from '@/components/ui/Toast';

const ToastContext = createContext(null);
let nextId = 0;
const MAX_TOASTS = 4;
const AUTO_DISMISS_MS = 4600;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (variant, message, detail) => {
      const id = ++nextId;
      setToasts((current) => [...current, { id, variant, message, detail }].slice(-MAX_TOASTS));
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss]
  );

  const toast = useMemo(
    () => ({
      success: (message, detail) => push('success', message, detail),
      error: (message, detail) => push('error', message, detail),
      info: (message, detail) => push('info', message, detail),
      warning: (message, detail) => push('warning', message, detail),
    }),
    [push]
  );

  const value = useMemo(() => ({ toast, toasts, dismiss }), [toast, toasts, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

/**
 * Returns the toast API itself (`success` / `error` / `info` / `warning`), so
 * call sites read `toast.success(...)`. The viewport is rendered by the
 * provider, so no consumer needs the queue or the dismiss handler.
 */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx.toast;
}
