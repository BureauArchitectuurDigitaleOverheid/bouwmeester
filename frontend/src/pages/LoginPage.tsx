import { useState } from 'react';
import { Fingerprint, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { authenticateWithBiometric, getStoredPersonId } from '@/api/webauthn';

export function LoginPage() {
  const { login, refreshAuthStatus, authError, canBiometricReauth } = useAuth();
  const [biometricLoading, setBiometricLoading] = useState(false);
  const [biometricError, setBiometricError] = useState<string | null>(null);

  const handleBiometricLogin = async () => {
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
      if (err instanceof Error && (err.message.includes('NotAllowed') || err.message.includes('AbortError'))) {
        setBiometricError(null); // User cancelled
      } else {
        setBiometricError('Biometrische inlog mislukt. Gebruik SSO om in te loggen.');
      }
    } finally {
      setBiometricLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-sm w-full space-y-6 text-center">
        <div>
          <h1 className="text-2xl font-semibold text-text">Bouwmeester</h1>
          <p className="mt-2 text-sm text-text-secondary">
            Log in om door te gaan
          </p>
        </div>
        {(authError || biometricError) && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {biometricError || 'Er ging iets mis bij het inloggen. Probeer het opnieuw of neem contact op met een beheerder.'}
          </div>
        )}

        {canBiometricReauth && (
          <button
            onClick={handleBiometricLogin}
            disabled={biometricLoading}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors disabled:opacity-50"
          >
            {biometricLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Fingerprint className="h-4 w-4" />
            )}
            Biometrisch inloggen
          </button>
        )}

        <button
          onClick={login}
          className={`w-full flex justify-center py-2.5 px-4 rounded-lg shadow-sm text-sm font-medium transition-colors ${
            canBiometricReauth
              ? 'border border-border text-text hover:bg-gray-100'
              : 'border border-transparent text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500'
          }`}
        >
          Inloggen met SSO Rijk
        </button>
      </div>
    </div>
  );
}
