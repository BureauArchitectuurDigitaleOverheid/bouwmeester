import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type {
  Initiatief,
  InitiatiefCreate,
  InitiatiefDetail,
  InitiatiefEenheid,
  InitiatiefMember,
  InitiatiefUpdate,
} from '@/types';

export async function getInitiatieven(params?: {
  search?: string;
}): Promise<Initiatief[]> {
  const query: Record<string, string> = {};
  if (params?.search) query.search = params.search;
  return apiGet<Initiatief[]>('/api/initiatieven', query);
}

export async function getInitiatief(id: string): Promise<InitiatiefDetail> {
  return apiGet<InitiatiefDetail>(`/api/initiatieven/${id}`);
}

export async function createInitiatief(data: InitiatiefCreate): Promise<Initiatief> {
  return apiPost<Initiatief>('/api/initiatieven', data);
}

export async function updateInitiatief(
  id: string,
  data: InitiatiefUpdate,
): Promise<Initiatief> {
  return apiPut<Initiatief>(`/api/initiatieven/${id}`, data);
}

export async function deleteInitiatief(id: string): Promise<void> {
  return apiDelete(`/api/initiatieven/${id}`);
}

export async function addInitiatiefMember(
  initiatiefId: string,
  personId: string,
  rol: string = 'contributor',
): Promise<InitiatiefMember> {
  return apiPost<InitiatiefMember>(`/api/initiatieven/${initiatiefId}/members`, {
    person_id: personId,
    rol,
  });
}

export async function removeInitiatiefMember(
  initiatiefId: string,
  personId: string,
): Promise<void> {
  return apiDelete(`/api/initiatieven/${initiatiefId}/members/${personId}`);
}

export async function updateInitiatiefMemberRole(
  initiatiefId: string,
  personId: string,
  rol: string,
): Promise<InitiatiefMember> {
  return apiPut<InitiatiefMember>(
    `/api/initiatieven/${initiatiefId}/members/${personId}`,
    { person_id: personId, rol },
  );
}

export async function addInitiatiefEenheid(
  initiatiefId: string,
  eenheidId: string,
): Promise<InitiatiefEenheid> {
  return apiPost<InitiatiefEenheid>(`/api/initiatieven/${initiatiefId}/eenheden`, {
    eenheid_id: eenheidId,
  });
}

export async function removeInitiatiefEenheid(
  initiatiefId: string,
  eenheidId: string,
): Promise<void> {
  return apiDelete(`/api/initiatieven/${initiatiefId}/eenheden/${eenheidId}`);
}
