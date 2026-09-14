import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import * as authService from '@/services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);
  const fetching = useRef(false);

  // Re-fetch the NEXUS profile whenever the Supabase auth state changes.
  const refresh = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      setUser(await authService.getSession());
    } finally {
      fetching.current = false;
    }
  }, []);

  const signup = useCallback(async ({ name, email, password }) => {
    const profile = await authService.signUp({ name, email, password });
    setUser(profile);
    return profile;
  }, []);

  useEffect(() => {
    // Initial restore: a persisted Supabase session → NEXUS profile.
    authService
      .getSession()
      .then(setUser)
      .finally(() => setInitializing(false));

    const unsubscribe = authService.onAuthChange(({ event, session }) => {
      if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        refresh();
      }
    });
    return () => {
      unsubscribe();
    };
  }, [refresh]);

  const login = useCallback(async (email, password) => {
    const profile = await authService.login({ email, password });
    setUser(profile);
    return profile;
  }, []);

  const logout = useCallback(async () => {
    await authService.logout();
    setUser(null);
  }, []);


  const value = useMemo(
    () => ({
      user,
      initializing,
      login,
      signup,
      logout,
      isAuthenticated: Boolean(user),
    }),
    [user, initializing, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
