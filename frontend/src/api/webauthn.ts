import { startRegistration, startAuthentication } from '@simplewebauthn/browser';
import { apiGet, apiPost, apiDelete } from '@/api/client';

export interface WebAuthnCredential {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
}

export async function listCredentials(): Promise<WebAuthnCredential[]> {
  return apiGet<WebAuthnCredential[]>('/api/webauthn/credentials');
}

export async function deleteCredential(id: string): Promise<void> {
  return apiDelete(`/api/webauthn/credentials/${id}`);
}

export async function registerCredential(label: string): Promise<WebAuthnCredential> {
  // 1. Get registration options from the server.
  const { options_json } = await apiPost<{ options_json: string }>('/api/webauthn/register/options');
  const options = JSON.parse(options_json);

  // 2. Prompt the browser for biometric registration.
  const credential = await startRegistration({ optionsJSON: options });

  // 3. Send the attestation back to the server for verification.
  return apiPost<WebAuthnCredential>('/api/webauthn/register/verify', {
    credential: JSON.stringify(credential),
    label,
  });
}

export async function authenticateWithBiometric(personId: string): Promise<boolean> {
  // 1. Get authentication options from the server.
  const { options_json } = await apiPost<{ options_json: string }>('/api/webauthn/authenticate/options', {
    person_id: personId,
  });
  const options = JSON.parse(options_json);

  // 2. Prompt the browser for biometric authentication.
  const credential = await startAuthentication({ optionsJSON: options });

  // 3. Send the assertion back to the server for verification.
  const result = await apiPost<{ authenticated: boolean }>('/api/webauthn/authenticate/verify', {
    person_id: personId,
    credential: JSON.stringify(credential),
  });

  return result.authenticated;
}

/** Check if WebAuthn is available in this browser. */
export function isWebAuthnAvailable(): boolean {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential;
}

const WEBAUTHN_PERSON_ID_KEY = 'bm_webauthn_person_id';

export function getStoredPersonId(): string | null {
  try {
    return localStorage.getItem(WEBAUTHN_PERSON_ID_KEY);
  } catch {
    return null;
  }
}

export function setStoredPersonId(personId: string): void {
  try {
    localStorage.setItem(WEBAUTHN_PERSON_ID_KEY, personId);
  } catch {
    // localStorage unavailable
  }
}

export function clearStoredPersonId(): void {
  try {
    localStorage.removeItem(WEBAUTHN_PERSON_ID_KEY);
  } catch {
    // localStorage unavailable
  }
}

/** Returns true if the error indicates the user cancelled the WebAuthn prompt. */
export function isWebAuthnCancellation(err: unknown): boolean {
  if (err instanceof Error) {
    return err.name === 'NotAllowedError' || err.name === 'AbortError';
  }
  return false;
}
