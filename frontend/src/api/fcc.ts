import { apiGet, apiPost } from './client';
import type {
  FccSchemaResponse,
  FccSyncLog,
  FccSyncTriggerResponse,
  Opdracht,
} from '@/types';

export async function triggerFccSync(): Promise<FccSyncTriggerResponse> {
  return apiPost<FccSyncTriggerResponse>('/api/fcc/sync/trigger');
}

export async function getFccSyncLogs(opdracht_id?: string): Promise<FccSyncLog[]> {
  const params: Record<string, string> = {};
  if (opdracht_id) params.opdracht_id = opdracht_id;
  return apiGet<FccSyncLog[]>('/api/fcc/sync/logs', params);
}

export async function getFccSchema(): Promise<FccSchemaResponse> {
  return apiGet<FccSchemaResponse>('/api/fcc/schema');
}

export async function getFccConflicts(): Promise<Opdracht[]> {
  return apiGet<Opdracht[]>('/api/fcc/conflicts');
}

export async function resolveFccConflict(
  opdrachtId: string,
  resolution: 'use_ours' | 'use_theirs',
): Promise<Opdracht> {
  return apiPost<Opdracht>(`/api/fcc/conflicts/${opdrachtId}/resolve`, {
    resolution,
  });
}

export async function pushOpdrachtToFcc(opdrachtId: string): Promise<Opdracht> {
  return apiPost<Opdracht>(`/api/fcc/opdrachten/${opdrachtId}/push`);
}
