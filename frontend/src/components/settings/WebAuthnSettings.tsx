import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Fingerprint, Trash2, Plus, Loader2 } from 'lucide-react';
import {
  listCredentials,
  deleteCredential,
  registerCredential,
  isWebAuthnAvailable,
  isWebAuthnCancellation,
  clearStoredPersonId,
  setStoredPersonId,
} from '@/api/webauthn';
import { useAuth } from '@/contexts/AuthContext';

export function WebAuthnSettings() {
  const { person } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { data: credentials, isLoading } = useQuery({
    queryKey: ['webauthn-credentials'],
    queryFn: listCredentials,
  });

  const registerMutation = useMutation({
    mutationFn: () => registerCredential('Biometrie'),
    onSuccess: () => {
      setError(null);
      setSuccess('Biometrische inlog is geregistreerd');
      // Store person_id in localStorage for biometric re-auth.
      if (person?.id) {
        setStoredPersonId(person.id);
      }
      queryClient.invalidateQueries({ queryKey: ['webauthn-credentials'] });
      setTimeout(() => setSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setSuccess(null);
      if (isWebAuthnCancellation(err)) {
        setError('Registratie geannuleerd');
      } else {
        setError('Registratie mislukt. Probeer het opnieuw.');
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCredential,
    onSuccess: (_data, deletedId) => {
      // If we just deleted the last credential, clear the stored person ID
      // so the biometric login button no longer appears on the login page.
      if (credentials && credentials.length === 1 && credentials[0].id === deletedId) {
        clearStoredPersonId();
      }
      queryClient.invalidateQueries({ queryKey: ['webauthn-credentials'] });
    },
  });

  if (!isWebAuthnAvailable()) {
    return (
      <div className="rounded-xl border border-border bg-surface p-6">
        <h2 className="text-base font-semibold text-text mb-2">Biometrische inlog</h2>
        <p className="text-sm text-text-secondary">
          Je browser ondersteunt geen biometrische inlog (WebAuthn). Gebruik een moderne browser om deze functie te gebruiken.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary-100">
          <Fingerprint className="h-5 w-5 text-primary-700" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-text">Biometrische inlog</h2>
          <p className="text-sm text-text-secondary">
            Gebruik Face ID, vingerafdruk of Windows Hello om snel opnieuw in te loggen.
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-700">
          {success}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-text-secondary py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          Laden...
        </div>
      ) : (
        <>
          {credentials && credentials.length > 0 && (
            <div className="mb-4 space-y-2">
              {credentials.map((cred) => (
                <div
                  key={cred.id}
                  className="flex items-center justify-between rounded-lg border border-border px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <Fingerprint className="h-4 w-4 text-text-secondary" />
                    <div>
                      <p className="text-sm font-medium text-text">{cred.label}</p>
                      <p className="text-xs text-text-secondary">
                        Geregistreerd {new Date(cred.created_at).toLocaleDateString('nl-NL')}
                        {cred.last_used_at && (
                          <> &middot; Laatst gebruikt {new Date(cred.last_used_at).toLocaleDateString('nl-NL')}</>
                        )}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      if (window.confirm('Weet je zeker dat je deze biometrische inlog wilt verwijderen?')) {
                        deleteMutation.mutate(cred.id);
                      }
                    }}
                    disabled={deleteMutation.isPending}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Verwijderen
                  </button>
                </div>
              ))}
            </div>
          )}

          <button
            onClick={() => registerMutation.mutate()}
            disabled={registerMutation.isPending}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {registerMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Registreer biometrische inlog
          </button>
        </>
      )}
    </div>
  );
}
