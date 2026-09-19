import { useCallback, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { authenticateWithBiometric, getStoredPersonId, isWebAuthnCancellation } from '@/api/webauthn';
import { useNlddEvent } from '@/components/nldd/events';
import { NlddButton } from '@/components/nldd/NlddLink';
import logoImg from '/logo.png?url';

export function LoginPage() {
  const { login, refreshAuthStatus, authError, canBiometricReauth } = useAuth();
  const [biometricLoading, setBiometricLoading] = useState(false);
  const [biometricError, setBiometricError] = useState<string | null>(null);
  const loginRef = useRef<HTMLElement>(null);

  const handleBiometricLogin = useCallback(async () => {
    const personId = getStoredPersonId();
    if (!personId) return;

    setBiometricLoading(true);
    setBiometricError(null);

    try {
      const success = await authenticateWithBiometric(personId);
      if (success) {
        await refreshAuthStatus();
      } else {
        setBiometricError('Biometrische verificatie mislukt. Probeer het opnieuw.');
      }
    } catch (err) {
      if (isWebAuthnCancellation(err)) {
        setBiometricError(null); // User cancelled
      } else {
        setBiometricError('Biometrische inlog mislukt. Gebruik SSO om in te loggen.');
      }
    } finally {
      setBiometricLoading(false);
    }
  }, [refreshAuthStatus]);

  useNlddEvent(loginRef, 'click', login);

  const errorMessage =
    biometricError ||
    (authError ? 'Er ging iets mis bij het inloggen. Probeer het opnieuw of neem contact op met een beheerder.' : null);

  return (
    <nldd-app-view background="tinted">
      <nldd-simple-section width="400px" horizontal-alignment="left" vertical-alignment="center">
        <nldd-container gap="24" horizontal-alignment="center" style={{ textAlign: 'center' }}>
          <nldd-container gap="12" horizontal-alignment="center">
            <nldd-image src={logoImg} alt="Bouwmeester" width="80" height={80} shape="circle" />
            <nldd-title size={3}>
              <h1>Bouwmeester</h1>
            </nldd-title>
            <nldd-text color="secondary">Log in om door te gaan</nldd-text>
          </nldd-container>

          {errorMessage && <nldd-banner variant="critical" size="sm" text={errorMessage} />}

          {canBiometricReauth && (
            <NlddButton
              text="Biometrisch inloggen"
              startIcon="key"
              loading={biometricLoading}
              disabled={biometricLoading}
              onClick={handleBiometricLogin}
              width="full"
            />
          )}

          <nldd-button
            ref={loginRef}
            text="Inloggen met SSO Rijk"
            variant={canBiometricReauth ? 'secondary' : 'primary'}
            width="full"
          />
        </nldd-container>
      </nldd-simple-section>
    </nldd-app-view>
  );
}
