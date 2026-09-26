import { apiGet, apiPost } from './client';
import type {
  FccSchemaResponse,
  FccSyncTriggerResponse,
} from '@/types';

export async function triggerFccSync(): Promise<FccSyncTriggerResponse> {
  return apiPost<FccSyncTriggerResponse>('/api/fcc/sync/trigger');
}

export async function getFccSchema(): Promise<FccSchemaResponse> {
  return apiGet<FccSchemaResponse>('/api/fcc/schema');
}

export async function getLastFccSync(): Promise<{ last_synced_at: string | null }> {
  return apiGet<{ last_synced_at: string | null }>('/api/fcc/sync/last');
}
