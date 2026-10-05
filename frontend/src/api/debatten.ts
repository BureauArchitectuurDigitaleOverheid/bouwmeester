import { apiGet, apiPost } from './client';
import type { AankomendeDebatten, DebatStartResult } from '@/types/debat';

export async function getAankomendeDebatten(): Promise<AankomendeDebatten> {
  return apiGet<AankomendeDebatten>('/api/debatten/aankomend');
}

export async function startDebat(activiteitId: string, teamId: string): Promise<DebatStartResult> {
  return apiPost<DebatStartResult>('/api/debatten/start', {
    activiteit_id: activiteitId,
    team_id: teamId,
  });
}
