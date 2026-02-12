import { useState, useEffect, useCallback } from 'react';
import { BASE_URL, getCsrfToken } from '@/api/client';

interface AccessDeniedPageProps {
  email: string | null;
}

type RequestState =
  | { step: 'idle' }
  | { step: 'form' }
  | { step: 'submitting' }
  | { step: 'pending' }
  | { step: 'approved' }
  | { step: 'denied'; reason?: string }
  | { step: 'error'; message: string }
  | { step: 'already_pending' };

export function AccessDeniedPage({ email }: AccessDeniedPageProps) {
  const [state, setState] = useState<RequestState>({ step: 'idle' });
  const [naam, setNaam] = useState('');

  const handleLogout = () => {
    window.location.href = `${BASE_URL}/api/auth/logout`;
  };

  // Check for existing pending request on mount
  useEffect(() => {
    if (!email) return;
    fetch(`${BASE_URL}/api/auth/access-request-status?email=${encodeURIComponent(email)}`, {
      credentials: 'include',
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.status === 'pending') {
          setState({ step: 'pending' });
        } else if (data.status === 'denied') {
          setState({ step: 'denied', reason: data.deny_reason });
        } else if (data.status === 'approved') {
          setState({ step: 'approved' });
        }
      })
      .catch(() => {
        // Ignore — stay on idle
      });
  }, [email]);

  // Poll for status changes while pending
  useEffect(() => {
    if (state.step !== 'pending' || !email) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(
          `${BASE_URL}/api/auth/access-request-status?email=${encodeURIComponent(email)}`,
          { credentials: 'include' }
        );
        const data = await res.json();
        if (data.status === 'approved') {
          setState({ step: 'approved' });
        } else if (data.status === 'denied') {
          setState({ step: 'denied', reason: data.deny_reason });
        }
      } catch {
        // Ignore polling errors
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [state.step, email]);

  // Auto-reload when approved
  useEffect(() => {
    if (state.step === 'approved') {
      const timer = setTimeout(() => window.location.reload(), 1500);
      return () => clearTimeout(timer);
    }
  }, [state.step]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!email || !naam.trim()) return;

      setState({ step: 'submitting' });
      try {
        const res = await fetch(`${BASE_URL}/api/auth/request-access`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': getCsrfToken(),
          },
          credentials: 'include',
          body: JSON.stringify({ email, naam: naam.trim() }),
        });

        if (!res.ok) {
          if (res.status === 429) {
            setState({ step: 'error', message: 'Te veel verzoeken, probeer het later opnieuw.' });
            return;
          }
          setState({ step: 'error', message: 'Er ging iets mis. Probeer het later opnieuw.' });
          return;
        }

        const data = await res.json();
        if (data.status === 'already_allowed') {
          setState({ step: 'approved' });
        } else if (data.status === 'already_pending') {
          setState({ step: 'already_pending' });
        } else {
          setState({ step: 'pending' });
        }
      } catch {
        setState({ step: 'error', message: 'Verbindingsfout. Probeer het later opnieuw.' });
      }
    },
    [email, naam]
  );

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-6 text-center">
        <div>
          <h1 className="text-2xl font-semibold text-text">Bouwmeester</h1>
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-6">
            <h2 className="text-lg font-medium text-amber-800">Geen toegang</h2>
            {email && (
              <p className="mt-2 text-sm text-amber-700">
                Ingelogd als <span className="font-medium">{email}</span>
              </p>
            )}

            {/* Idle state — show request button */}
            {state.step === 'idle' && (
              <>
                <p className="mt-3 text-sm text-amber-700">
                  Je account staat niet op de toegangslijst voor deze applicatie.
                </p>
                <button
                  onClick={() => setState({ step: 'form' })}
                  className="mt-4 w-full flex justify-center py-2.5 px-4 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                >
                  Toegang aanvragen
                </button>
              </>
            )}

            {/* Form state — name input */}
            {state.step === 'form' && (
              <form onSubmit={handleSubmit} className="mt-4 space-y-3">
                <p className="text-sm text-amber-700 text-left">
                  Vul je naam in om toegang aan te vragen.
                </p>
                <input
                  type="text"
                  value={naam}
                  onChange={(e) => setNaam(e.target.value)}
                  placeholder="Je volledige naam"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
                  required
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={!naam.trim()}
                  className="w-full flex justify-center py-2.5 px-4 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
                >
                  Verzoek versturen
                </button>
              </form>
            )}

            {/* Submitting */}
            {state.step === 'submitting' && (
              <p className="mt-3 text-sm text-amber-700">Verzoek wordt verstuurd...</p>
            )}

            {/* Pending state */}
            {(state.step === 'pending' || state.step === 'already_pending') && (
              <div className="mt-3">
                <p className="text-sm text-green-700">
                  Je verzoek is verstuurd. Een beheerder zal je verzoek beoordelen.
                </p>
                <div className="mt-2 flex items-center justify-center gap-2 text-xs text-amber-600">
                  <span className="inline-block h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
                  Wachten op goedkeuring...
                </div>
              </div>
            )}

            {/* Approved state */}
            {state.step === 'approved' && (
              <div className="mt-3">
                <p className="text-sm text-green-700 font-medium">
                  Je toegang is goedgekeurd! Pagina wordt herladen...
                </p>
              </div>
            )}

            {/* Denied state */}
            {state.step === 'denied' && (
              <div className="mt-3">
                <p className="text-sm text-red-700">
                  Je verzoek is afgewezen.
                  {state.reason && (
                    <span className="block mt-1 text-red-600">Reden: {state.reason}</span>
                  )}
                </p>
                <button
                  onClick={() => setState({ step: 'form' })}
                  className="mt-3 w-full flex justify-center py-2.5 px-4 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                >
                  Opnieuw aanvragen
                </button>
              </div>
            )}

            {/* Error state */}
            {state.step === 'error' && (
              <div className="mt-3">
                <p className="text-sm text-red-700">{state.message}</p>
                <button
                  onClick={() => setState({ step: 'idle' })}
                  className="mt-3 text-sm text-primary-600 hover:text-primary-800 transition-colors"
                >
                  Opnieuw proberen
                </button>
              </div>
            )}
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="w-full flex justify-center py-2.5 px-4 border border-border rounded-lg shadow-sm text-sm font-medium text-text hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors"
        >
          Uitloggen en opnieuw proberen
        </button>
      </div>
    </div>
  );
}
