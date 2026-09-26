import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { BASE_URL } from '@/api/client';
import { getStoredPersonId, isWebAuthnAvailable } from '@/api/webauthn';

interface OrgEenheid {
  id: string;
  naam: string;
  type: string | null;
}

export interface OnboardingFeature {
  key: string;
  label: string;
  dismissible: boolean;
  blocking: boolean;
}

interface AuthPerson {
  sub: string;
  email: string;
  name: string;
  id: string | null;
  needs_onboarding: boolean;
  onboarding_features: OnboardingFeature[];
  is_admin: boolean;
  managed_eenheden: OrgEenheid[];
  needs_placement: boolean;
  has_pending_placement: boolean;
  placement_denied: boolean;
  roles?: { role_id: string; role_naam: string | null; organisatie_eenheid_id: string | null; eenheid_naam: string | null }[];
  permissions?: string[];
  system_permissions?: string[];
  /** Eenheden whose members this person manages; "*" means all. */
  managed_subtree_ids?: string[];
}

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  oidcConfigured: boolean;
  webauthnSession: boolean;
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
  canPasskeyLogin: boolean;
  realIsAdmin: boolean;
  viewAsNonAdmin: boolean;
  toggleViewAsNonAdmin: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * The backend was out of reach, not wrong: no response at all, or a 5xx.
 *
 * In production the API lives on its own origin (component-2), so a backend
 * that is restarting after a deploy answers from the ingress without CORS
 * headers, and the browser reports that as a bare `TypeError: Failed to fetch`.
 * The same happens for a laptop that wakes up before its Wi-Fi does. Both pass
 * within seconds, so they are worth waiting out rather than showing.
 */
class TransientAuthError extends Error {}

const UNREACHABLE_MESSAGE = 'Bouwmeester is even niet bereikbaar. We proberen het automatisch opnieuw.';

/**
 * Backoff for the first check: 45 seconds in total before giving up. A
 * backend deploy was measured at 37 seconds of 503s (2026-09-25): the pod
 * holds a volume only one pod can mount, so the old one stops before the new
 * one starts. The whole window fits inside this, so a deploy shows "Laden..."
 * rather than an error.
 */
const RETRY_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 15_000, 15_000];

/** How often the error screen tries again on its own. */
const RECOVERY_INTERVAL_MS = 10_000;

async function fetchAuthStatus(): Promise<AuthState> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/api/auth/status`, { credentials: 'include' });
  } catch {
    throw new TransientAuthError(UNREACHABLE_MESSAGE);
  }
  if (res.status >= 500) throw new TransientAuthError(UNREACHABLE_MESSAGE);
  if (!res.ok) throw new Error(`Auth status check failed: ${res.status}`);
  const data = await res.json();
  return {
    loading: false,
    authenticated: data.authenticated,
    oidcConfigured: data.oidc_configured,
    webauthnSession: data.webauthn_session ?? false,
    person: data.person
      ? {
          sub: data.person.sub ?? '',
          email: data.person.email ?? '',
          name: data.person.name ?? '',
          id: data.person.id ?? null,
          needs_onboarding: data.person.needs_onboarding ?? false,
          onboarding_features: data.person.onboarding_features ?? [],
          is_admin: data.person.is_admin ?? false,
          managed_eenheden: data.person.managed_eenheden ?? [],
          needs_placement: data.person.needs_placement ?? false,
          has_pending_placement: data.person.has_pending_placement ?? false,
          placement_denied: data.person.placement_denied ?? false,
          roles: data.person.roles ?? [],
          permissions: data.person.permissions ?? [],
          system_permissions: data.person.system_permissions ?? [],
          managed_subtree_ids: data.person.managed_subtree_ids ?? [],
        }
      : null,
    error: null,
    authError: data.error ?? null,
    accessDenied: data.access_denied ?? false,
    deniedEmail: data.denied_email ?? null,
  };
}

/** `fetchAuthStatus`, retried with backoff while the failure is transient. */
async function fetchAuthStatusWithRetry(isCancelled: () => boolean): Promise<AuthState> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetchAuthStatus();
    } catch (err) {
      const delay = RETRY_DELAYS_MS[attempt];
      if (!(err instanceof TransientAuthError) || delay === undefined || isCancelled()) throw err;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true,
    authenticated: false,
    oidcConfigured: false,
    webauthnSession: false,
    person: null,
    error: null,
    authError: null,
    accessDenied: false,
    deniedEmail: null,
  });

  useEffect(() => {
    let cancelled = false;
    fetchAuthStatusWithRetry(() => cancelled)
      .then((s) => {
        if (!cancelled) setState(s);
      })
      .catch((err) => {
        if (cancelled) return;
        setState((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : 'Kon authenticatiestatus niet ophalen',
        }));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Once the error screen is up, keep trying on our own: every few seconds, and
  // straight away when the browser says the network is back. The first answer
  // that gets through replaces the error with the real state, so a deploy that
  // outlasts the backoff above still ends without anyone pressing a button.
  const hasError = state.error !== null;
  useEffect(() => {
    if (!hasError) return;
    let cancelled = false;
    const tryAgain = () => {
      fetchAuthStatus()
        .then((s) => {
          if (!cancelled) setState(s);
        })
        .catch(() => {
          // Still out of reach; the next tick tries again.
        });
    };
    const interval = setInterval(tryAgain, RECOVERY_INTERVAL_MS);
    window.addEventListener('online', tryAgain);
    return () => {
      cancelled = true;
      clearInterval(interval);
      window.removeEventListener('online', tryAgain);
    };
  }, [hasError]);

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
    // Intentionally NOT clearing the stored passkey person ID here.
    // If the user has registered a passkey, they should see
    // the passkey login button after logout. If a different person uses
    // the device, the passkey check will simply fail
    // and they can use SSO instead.

    // Clear cached API responses to prevent data leakage across sessions
    if ('caches' in window) {
      await caches.delete('api-cache').catch(() => {});
    }
    window.location.href = `${BASE_URL}/api/auth/logout`;
  }, []);

  // Recalculated on every render (both calls are trivial) so it picks up
  // localStorage changes after registration or logout.
  const canPasskeyLogin = isWebAuthnAvailable() && !!getStoredPersonId();

  const [viewAsNonAdmin, setViewAsNonAdmin] = useState(false);
  const toggleViewAsNonAdmin = useCallback(() => setViewAsNonAdmin((prev) => !prev), []);
  const realIsAdmin = state.person?.is_admin ?? false;

  const effectiveState = useMemo(() => {
    if (!viewAsNonAdmin || !state.person) return state;
    return {
      ...state,
      person: {
        ...state.person,
        is_admin: false,
        roles: [],
        permissions: ['node:read', 'task:read', 'edge:read', 'lead:read', 'initiatief:read', 'opdracht:read', 'tag:read', 'people:read', 'org:read'],
      },
    };
  }, [state, viewAsNonAdmin]);

  const value: AuthContextValue = {
    ...effectiveState,
    login,
    logout,
    refreshAuthStatus,
    canPasskeyLogin,
    realIsAdmin,
    viewAsNonAdmin,
    toggleViewAsNonAdmin,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
