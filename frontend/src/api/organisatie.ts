import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type {
  OrganisatieEenheid,
  OrganisatieEenheidCreate,
  OrganisatieEenheidUpdate,
  OrganisatieEenheidTreeNode,
  OrganisatieEenheidPersonenGroup,
  Person,
} from '@/types';

export async function getOrganisatieTree(): Promise<OrganisatieEenheidTreeNode[]> {
  return apiGet<OrganisatieEenheidTreeNode[]>('/api/organisatie', { format: 'tree' });
}

export async function getOrganisatieFlat(): Promise<OrganisatieEenheid[]> {
  return apiGet<OrganisatieEenheid[]>('/api/organisatie');
}

export async function getOrganisatieEenheid(id: string): Promise<OrganisatieEenheid> {
  return apiGet<OrganisatieEenheid>(`/api/organisatie/${id}`);
}

export async function createOrganisatieEenheid(
  data: OrganisatieEenheidCreate,
): Promise<OrganisatieEenheid> {
  return apiPost<OrganisatieEenheid>('/api/organisatie', data);
}

export async function updateOrganisatieEenheid(
  id: string,
  data: OrganisatieEenheidUpdate,
): Promise<OrganisatieEenheid> {
  return apiPut<OrganisatieEenheid>(`/api/organisatie/${id}`, data);
}

export async function deleteOrganisatieEenheid(id: string): Promise<void> {
  return apiDelete(`/api/organisatie/${id}`);
}

export async function getOrganisatiePersonen(id: string): Promise<Person[]> {
  return apiGet<Person[]>(`/api/organisatie/${id}/personen`);
}

export async function getOrganisatiePersonenRecursive(id: string): Promise<OrganisatieEenheidPersonenGroup> {
  return apiGet<OrganisatieEenheidPersonenGroup>(`/api/organisatie/${id}/personen`, { recursive: true });
}

