import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Person, PersonCreate, PersonSummaryResponse, PersonOrganisatie, PersonEmail, PersonPhone, ApiKeyResponse } from '@/types';

export async function getPeople(): Promise<Person[]> {
  return apiGet<Person[]>('/api/people', { limit: '1000' });
}

export async function getPerson(id: string): Promise<Person> {
  return apiGet<Person>(`/api/people/${id}`);
}

export async function createPerson(data: PersonCreate): Promise<Person> {
  return apiPost<Person>('/api/people', data);
}

export async function updatePerson(id: string, data: Partial<PersonCreate>): Promise<Person> {
  return apiPut<Person>(`/api/people/${id}`, data);
}

export async function getPersonSummary(id: string): Promise<PersonSummaryResponse> {
  return apiGet<PersonSummaryResponse>(`/api/people/${id}/summary`);
}

// Org placements
export async function getPersonOrganisaties(
  personId: string,
  actief = true,
): Promise<PersonOrganisatie[]> {
  return apiGet<PersonOrganisatie[]>(
    `/api/people/${personId}/organisaties?actief=${actief}`,
  );
}

export async function addPersonOrganisatie(
  personId: string,
  data: { organisatie_eenheid_id: string; dienstverband?: string; start_datum: string },
): Promise<PersonOrganisatie> {
  return apiPost<PersonOrganisatie>(`/api/people/${personId}/organisaties`, data);
}

export async function updatePersonOrganisatie(
  personId: string,
  placementId: string,
  data: { dienstverband?: string; eind_datum?: string | null },
): Promise<PersonOrganisatie> {
  return apiPut<PersonOrganisatie>(
    `/api/people/${personId}/organisaties/${placementId}`,
    data,
  );
}

export async function removePersonOrganisatie(
  personId: string,
  placementId: string,
): Promise<void> {
  return apiDelete(`/api/people/${personId}/organisaties/${placementId}`);
}

export async function rotateApiKey(personId: string): Promise<ApiKeyResponse> {
  return apiPost<ApiKeyResponse>(`/api/people/${personId}/rotate-api-key`);
}

export async function searchPeople(q: string, limit = 10): Promise<Person[]> {
  return apiGet<Person[]>('/api/people/search', { q, limit: String(limit) });
}

// Emails
export async function addPersonEmail(
  personId: string,
  data: { email: string; is_default?: boolean },
): Promise<PersonEmail> {
  return apiPost<PersonEmail>(`/api/people/${personId}/emails`, data);
}

export async function removePersonEmail(personId: string, emailId: string): Promise<void> {
  return apiDelete(`/api/people/${personId}/emails/${emailId}`);
}

export async function setDefaultEmail(personId: string, emailId: string): Promise<PersonEmail> {
  return apiPost<PersonEmail>(`/api/people/${personId}/emails/${emailId}/set-default`, {});
}

// Phones
export async function addPersonPhone(
  personId: string,
  data: { phone_number: string; label: string; is_default?: boolean },
): Promise<PersonPhone> {
  return apiPost<PersonPhone>(`/api/people/${personId}/phones`, data);
}

export async function removePersonPhone(personId: string, phoneId: string): Promise<void> {
  return apiDelete(`/api/people/${personId}/phones/${phoneId}`);
}

export async function setDefaultPhone(personId: string, phoneId: string): Promise<PersonPhone> {
  return apiPost<PersonPhone>(`/api/people/${personId}/phones/${phoneId}/set-default`, {});
}
