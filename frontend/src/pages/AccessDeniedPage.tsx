import { useState, useEffect, useCallback, useRef } from 'react';
import { BASE_URL, getCsrfToken } from '@/api/client';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import { NlddButton } from '@/components/nldd/NlddLink';
import logoImg from '/logo.png?url';

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
  const naamFieldRef = useRef<HTMLElement>(null);

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

  useNlddEvent(naamFieldRef, 'input', (e) => setNaam(eventValue(e)));

  return (
    <nldd-app-view background="tinted">
      <nldd-simple-section width="480px" horizontal-alignment="left" vertical-alignment="center">
        <nldd-container gap="24" horizontal-alignment="center" style={{ textAlign: 'center' }}>
          <nldd-container gap="12" horizontal-alignment="center">
            <img src={logoImg} alt="Bouwmeester" style={{ width: '80px', height: '80px', borderRadius: '9999px' }} />
            <nldd-title size={3}>
              <h1>Bouwmeester</h1>
            </nldd-title>
          </nldd-container>

          <nldd-inline-dialog
            variant="alert"
            text="Geen toegang"
            {...(email ? { 'supporting-text': `Ingelogd als ${email}` } : {})}
          >
            <nldd-container gap="16" horizontal-alignment="center" style={{ marginTop: '16px' }}>
              {state.step === 'idle' && (
                <>
                  <nldd-text color="secondary">
                    Je account staat niet op de toegangslijst voor deze applicatie.
                  </nldd-text>
                  <NlddButton
                    text="Toegang aanvragen"
                    width="full"
                    onClick={() => setState({ step: 'form' })}
                  />
                </>
              )}

              {state.step === 'form' && (
                <form onSubmit={handleSubmit} style={{ width: '100%', textAlign: 'left' }}>
                  <nldd-container gap="12">
                    <nldd-form-field label="Je volledige naam">
                      <nldd-text-field
                        ref={naamFieldRef}
                        value={naam}
                        placeholder="Je volledige naam"
                        required
                        width="full"
                      />
                    </nldd-form-field>
                    <NlddButton
                      type="submit"
                      text="Verzoek versturen"
                      width="full"
                      disabled={!naam.trim()}
                    />
                  </nldd-container>
                </form>
              )}

              {state.step === 'submitting' && (
                <nldd-text color="secondary">Verzoek wordt verstuurd...</nldd-text>
              )}

              {(state.step === 'pending' || state.step === 'already_pending') && (
                <nldd-banner
                  variant="warning"
                  size="sm"
                  text="Je verzoek is verstuurd."
                  supporting-text="Een beheerder zal je verzoek beoordelen. Wachten op goedkeuring..."
                />
              )}

              {state.step === 'approved' && (
                <nldd-banner
                  variant="success"
                  size="sm"
                  text="Je toegang is goedgekeurd!"
                  supporting-text="Pagina wordt herladen..."
                />
              )}

              {state.step === 'denied' && (
                <>
                  <nldd-banner
                    variant="critical"
                    size="sm"
                    text="Je verzoek is afgewezen."
                    {...(state.reason ? { 'supporting-text': `Reden: ${state.reason}` } : {})}
                  />
                  <NlddButton
                    text="Opnieuw aanvragen"
                    width="full"
                    onClick={() => setState({ step: 'form' })}
                  />
                </>
              )}

              {state.step === 'error' && (
                <>
                  <nldd-text color="critical">{state.message}</nldd-text>
                  <NlddButton
                    text="Opnieuw proberen"
                    variant="neutral-transparent"
                    onClick={() => setState({ step: 'idle' })}
                  />
                </>
              )}
            </nldd-container>
          </nldd-inline-dialog>

          <NlddButton
            text="Uitloggen en opnieuw proberen"
            variant="secondary"
            width="full"
            onClick={handleLogout}
          />
        </nldd-container>
      </nldd-simple-section>
    </nldd-app-view>
  );
}
