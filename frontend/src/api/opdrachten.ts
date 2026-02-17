import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Opdracht, OpdrachtCreate, OpdrachtUpdate, OpdrachtNodeCreate, OpdrachtNodeResponse, FinancieelOverzicht, OpdrachtenSummary } from '@/types';

export async function getOpdrachten(params?: {
  begrotingsjaar?: number;
  type?: string;
  status?: string;
  instrument_id?: string;
  opdrachtnemer_id?: string;
  opdrachtgever_id?: string;
  verantwoordelijke_id?: string;
}): Promise<Opdracht[]> {
  return apiGet<Opdracht[]>('/api/opdrachten', params as Record<string, string | number | boolean | undefined>);
}

export async function getOpdrachtenSummary(params?: {
  begrotingsjaar?: number;
  type?: string;
  status?: string;
  opdrachtnemer_id?: string;
}): Promise<OpdrachtenSummary> {
  return apiGet<OpdrachtenSummary>('/api/opdrachten/summary', params as Record<string, string | number | boolean | undefined>);
}

export async function getOpdracht(id: string): Promise<Opdracht> {
  return apiGet<Opdracht>(`/api/opdrachten/${id}`);
}

export async function createOpdracht(data: OpdrachtCreate): Promise<Opdracht> {
  return apiPost<Opdracht>('/api/opdrachten', data);
}

export async function updateOpdracht(id: string, data: OpdrachtUpdate): Promise<Opdracht> {
  return apiPut<Opdracht>(`/api/opdrachten/${id}`, data);
}

export async function deleteOpdracht(id: string): Promise<void> {
  return apiDelete(`/api/opdrachten/${id}`);
}

export async function addOpdrachtNodeKoppeling(opdrachtId: string, data: OpdrachtNodeCreate): Promise<OpdrachtNodeResponse> {
  return apiPost<OpdrachtNodeResponse>(`/api/opdrachten/${opdrachtId}/koppelingen`, data);
}

export async function removeOpdrachtNodeKoppeling(opdrachtId: string, koppelingId: string): Promise<void> {
  return apiDelete(`/api/opdrachten/${opdrachtId}/koppelingen/${koppelingId}`);
}

export async function getNodeFinancieel(nodeId: string): Promise<FinancieelOverzicht> {
  return apiGet<FinancieelOverzicht>(`/api/nodes/${nodeId}/financieel`);
}

export async function getNodeOpdrachten(nodeId: string): Promise<Opdracht[]> {
  return apiGet<Opdracht[]>(`/api/nodes/${nodeId}/opdrachten`);
}
