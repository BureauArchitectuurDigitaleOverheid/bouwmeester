import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Opdracht, OpdrachtCreate, OpdrachtUpdate, OpdrachtNodeCreate, OpdrachtNodeResponse, FinancieelOverzicht, OpdrachtenSummary, OpdrachtMember, OpdrachtEenheid } from '@/types';

export async function getOpdrachten(params?: {
  begrotingsjaar?: number;
  type?: string;
  status?: string;
  instrument_id?: string;
  opdrachtnemer_eenheid_id?: string;
  opdrachtgever_id?: string;
  verantwoordelijke_id?: string;
}): Promise<Opdracht[]> {
  return apiGet<Opdracht[]>('/api/opdrachten', params as Record<string, string | number | boolean | undefined>);
}

export async function getOpdrachtenSummary(params?: {
  begrotingsjaar?: number;
  type?: string;
  status?: string;
  opdrachtnemer_eenheid_id?: string;
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

// --- Member (contactpersonen) ---

export async function addOpdrachtMember(
  opdrachtId: string,
  personId: string,
  rol: string = 'betrokken',
): Promise<OpdrachtMember> {
  return apiPost<OpdrachtMember>(`/api/opdrachten/${opdrachtId}/members`, {
    person_id: personId,
    rol,
  });
}

export async function removeOpdrachtMember(
  opdrachtId: string,
  personId: string,
): Promise<void> {
  return apiDelete(`/api/opdrachten/${opdrachtId}/members/${personId}`);
}

export async function updateOpdrachtMemberRole(
  opdrachtId: string,
  personId: string,
  rol: string,
): Promise<OpdrachtMember> {
  return apiPut<OpdrachtMember>(
    `/api/opdrachten/${opdrachtId}/members/${personId}`,
    { rol },
  );
}

// --- Eenheid (organisatie-eenheden) ---

export async function addOpdrachtEenheid(
  opdrachtId: string,
  eenheidId: string,
  rol: string = 'betrokken',
): Promise<OpdrachtEenheid> {
  return apiPost<OpdrachtEenheid>(`/api/opdrachten/${opdrachtId}/eenheden`, {
    eenheid_id: eenheidId,
    rol,
  });
}

export async function removeOpdrachtEenheid(
  opdrachtId: string,
  eenheidId: string,
): Promise<void> {
  return apiDelete(`/api/opdrachten/${opdrachtId}/eenheden/${eenheidId}`);
}

export async function updateOpdrachtEenheidRol(
  opdrachtId: string,
  eenheidId: string,
  rol: string,
): Promise<OpdrachtEenheid> {
  return apiPut<OpdrachtEenheid>(
    `/api/opdrachten/${opdrachtId}/eenheden/${eenheidId}`,
    { rol },
  );
}

// --- LLM matching ---

export async function matchOpdrachtContacts(
  opdrachtId: string,
): Promise<(OpdrachtMember | OpdrachtEenheid)[]> {
  return apiPost<(OpdrachtMember | OpdrachtEenheid)[]>(
    `/api/opdrachten/${opdrachtId}/match-contacts`,
    {},
  );
}

export async function matchOpdrachtContactsBulk(
  force: boolean = false,
): Promise<{ matched: number; skipped: number; total: number }> {
  return apiPost<{ matched: number; skipped: number; total: number }>(
    `/api/opdrachten/match-contacts-bulk?force=${force}`,
    {},
  );
}
