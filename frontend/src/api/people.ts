import { apiGet, apiPost, apiPut } from './client';
import type { Person, PersonCreate, PersonSummaryResponse } from '@/types';

export async function getPeople(): Promise<Person[]> {
  return apiGet<Person[]>('/api/people');
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
