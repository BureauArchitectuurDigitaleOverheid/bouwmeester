import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type {
  PersoonLidmaatschap,
  Samenwerkingsverband,
  SamenwerkingsverbandCreate,
  SamenwerkingsverbandDetail,
  SamenwerkingsverbandLid,
  SamenwerkingsverbandLidCreate,
  SamenwerkingsverbandLidUpdate,
  SamenwerkingsverbandUpdate,
} from '@/types';

export async function getSamenwerkingsverbanden(params?: {
  search?: string;
  type?: string;
  actief?: boolean;
}): Promise<Samenwerkingsverband[]> {
  const query: Record<string, string> = {};
  if (params?.search) query.search = params.search;
  if (params?.type) query.type = params.type;
  if (params?.actief !== undefined) query.actief = String(params.actief);
  return apiGet<Samenwerkingsverband[]>('/api/samenwerkingsverbanden', query);
}

export async function getSamenwerkingsverband(
  id: string,
): Promise<SamenwerkingsverbandDetail> {
  return apiGet<SamenwerkingsverbandDetail>(`/api/samenwerkingsverbanden/${id}`);
}

export async function createSamenwerkingsverband(
  data: SamenwerkingsverbandCreate,
): Promise<Samenwerkingsverband> {
  return apiPost<Samenwerkingsverband>('/api/samenwerkingsverbanden', data);
}

export async function updateSamenwerkingsverband(
  id: string,
  data: SamenwerkingsverbandUpdate,
): Promise<Samenwerkingsverband> {
  return apiPut<Samenwerkingsverband>(`/api/samenwerkingsverbanden/${id}`, data);
}

export async function deleteSamenwerkingsverband(id: string): Promise<void> {
  return apiDelete(`/api/samenwerkingsverbanden/${id}`);
}

// Leden
export async function listLeden(
  swvId: string,
  actief: boolean = true,
): Promise<SamenwerkingsverbandLid[]> {
  return apiGet<SamenwerkingsverbandLid[]>(
    `/api/samenwerkingsverbanden/${swvId}/leden`,
    { actief: String(actief) },
  );
}

export async function addLid(
  swvId: string,
  data: SamenwerkingsverbandLidCreate,
): Promise<SamenwerkingsverbandLid> {
  return apiPost<SamenwerkingsverbandLid>(
    `/api/samenwerkingsverbanden/${swvId}/leden`,
    data,
  );
}

export async function updateLid(
  swvId: string,
  lidId: string,
  data: SamenwerkingsverbandLidUpdate,
): Promise<SamenwerkingsverbandLid> {
  return apiPut<SamenwerkingsverbandLid>(
    `/api/samenwerkingsverbanden/${swvId}/leden/${lidId}`,
    data,
  );
}

export async function removeLid(swvId: string, lidId: string): Promise<void> {
  return apiDelete(`/api/samenwerkingsverbanden/${swvId}/leden/${lidId}`);
}

export async function listForPerson(
  personId: string,
  actief: boolean = true,
): Promise<PersoonLidmaatschap[]> {
  return apiGet<PersoonLidmaatschap[]>(
    `/api/samenwerkingsverbanden/by-person/${personId}`,
    { actief: String(actief) },
  );
}
