import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { BASE_URL } from '@/api/client';

interface AuthPerson {
  sub: string;
  email: string;
  name: string;
}

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  oidcConfigured: boolean;
  person: AuthPerson | null;
}

interface AuthContextValue extends AuthState {
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true,
    authenticated: false,
    oidcConfigured: false,
    person: null,
  });

  useEffect(() => {
    fetch(`${BASE_URL}/api/auth/status`, { credentials: 'include' })
      .then((res) => res.json())
      .then((data) => {
        setState({
          loading: false,
          authenticated: data.authenticated,
          oidcConfigured: data.oidc_configured,
          person: data.person ?? null,
        });
      })
      .catch(() => {
        setState((s) => ({ ...s, loading: false }));
      });
  }, []);

  const login = () => {
    window.location.href = `${BASE_URL}/api/auth/login`;
  };

  const logout = () => {
    window.location.href = `${BASE_URL}/api/auth/logout`;
  };

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
