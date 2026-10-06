import { apiGet, apiPost } from './client';
import type { AankomendeDebatten, DebatStartResult, DebatVolgenResult } from '@/types/debat';

export async function getAankomendeDebatten(): Promise<AankomendeDebatten> {
  return apiGet<AankomendeDebatten>('/api/debatten/aankomend');
}

export async function startDebat(activiteitId: string, teamId: string): Promise<DebatStartResult> {
  return apiPost<DebatStartResult>('/api/debatten/start', {
    activiteit_id: activiteitId,
    team_id: teamId,
  });
}

export async function stopDebat(sessieId: string): Promise<DebatVolgenResult> {
  return apiPost<DebatVolgenResult>(`/api/debatten/${encodeURIComponent(sessieId)}/stop`);
}

export async function hervatDebat(sessieId: string): Promise<DebatVolgenResult> {
  return apiPost<DebatVolgenResult>(`/api/debatten/${encodeURIComponent(sessieId)}/hervat`);
}
