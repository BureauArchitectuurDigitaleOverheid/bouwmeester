import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { ExterneOrganisatie, ExterneOrganisatieCreate, ExterneOrganisatieUpdate } from '@/types';

export async function getExterneOrganisaties(params?: {
  type?: string;
  search?: string;
}): Promise<ExterneOrganisatie[]> {
  return apiGet<ExterneOrganisatie[]>('/api/externe-organisaties', params);
}

export async function getExterneOrganisatie(id: string): Promise<ExterneOrganisatie> {
  return apiGet<ExterneOrganisatie>(`/api/externe-organisaties/${id}`);
}

export async function createExterneOrganisatie(data: ExterneOrganisatieCreate): Promise<ExterneOrganisatie> {
  return apiPost<ExterneOrganisatie>('/api/externe-organisaties', data);
}

export async function updateExterneOrganisatie(id: string, data: ExterneOrganisatieUpdate): Promise<ExterneOrganisatie> {
  return apiPut<ExterneOrganisatie>(`/api/externe-organisaties/${id}`, data);
}

export async function deleteExterneOrganisatie(id: string): Promise<void> {
  return apiDelete(`/api/externe-organisaties/${id}`);
}
