import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { BASE_URL } from '@/api/client';
import { getStoredPersonId, isWebAuthnAvailable } from '@/api/webauthn';

interface AuthPerson {
  sub: string;
  email: string;
  name: string;
  id: string | null;
  needs_onboarding: boolean;
  is_admin: boolean;
}

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  oidcConfigured: boolean;
  person: AuthPerson | null;
  error: string | null;
  authError: string | null;
  accessDenied: boolean;
  deniedEmail: string | null;
}

interface AuthContextValue extends AuthState {
  login: () => void;
  logout: () => void;
  refreshAuthStatus: () => Promise<void>;
  canBiometricReauth: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchAuthStatus(): Promise<AuthState> {
  const res = await fetch(`${BASE_URL}/api/auth/status`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Auth status check failed: ${res.status}`);
  const data = await res.json();
  return {
    loading: false,
    authenticated: data.authenticated,
    oidcConfigured: data.oidc_configured,
    person: data.person
      ? {
          sub: data.person.sub ?? '',
          email: data.person.email ?? '',
          name: data.person.name ?? '',
          id: data.person.id ?? null,
          needs_onboarding: data.person.needs_onboarding ?? false,
          is_admin: data.person.is_admin ?? false,
        }
      : null,
    error: null,
    authError: data.error ?? null,
    accessDenied: data.access_denied ?? false,
    deniedEmail: data.denied_email ?? null,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true,
    authenticated: false,
    oidcConfigured: false,
    person: null,
    error: null,
    authError: null,
    accessDenied: false,
    deniedEmail: null,
  });

  useEffect(() => {
    fetchAuthStatus()
      .then((s) => setState(s))
      .catch((err) => {
        setState((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : 'Kon authenticatiestatus niet ophalen',
        }));
      });
  }, []);

  const refreshAuthStatus = useCallback(async () => {
    try {
      const s = await fetchAuthStatus();
      setState(s);
    } catch {
      // Silently ignore refresh errors — the stale state is still usable
    }
  }, []);

  // Re-check auth when the app regains focus (e.g. after being backgrounded on mobile).
  // Throttled to at most once per 60 seconds to avoid hammering the backend.
  const lastRefreshRef = useRef(0);
  useEffect(() => {
    const throttledRefresh = () => {
      const now = Date.now();
      if (now - lastRefreshRef.current < 60_000) return;
      lastRefreshRef.current = now;
      refreshAuthStatus();
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') throttledRefresh();
    };
    const onFocus = () => throttledRefresh();

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', onFocus);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('focus', onFocus);
    };
  }, [refreshAuthStatus]);

  // Periodic background ping every 4 minutes to keep the Keycloak refresh token alive.
  useEffect(() => {
    if (!state.authenticated) return;
    const interval = setInterval(() => refreshAuthStatus(), 4 * 60 * 1000);
    return () => clearInterval(interval);
  }, [state.authenticated, refreshAuthStatus]);

  const login = useCallback(() => {
    window.location.href = `${BASE_URL}/api/auth/login`;
  }, []);

  const logout = useCallback(async () => {
    // Clear cached API responses to prevent data leakage across sessions
    if ('caches' in window) {
      await caches.delete('api-cache').catch(() => {});
    }
    window.location.href = `${BASE_URL}/api/auth/logout`;
  }, []);

  const canBiometricReauth = useMemo(
    () => isWebAuthnAvailable() && !!getStoredPersonId(),
    [],
  );

  return (
    <AuthContext.Provider value={{ ...state, login, logout, refreshAuthStatus, canBiometricReauth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
