import { apiGet } from './client';
import type { Activity } from '@/types';

export async function getActivityFeed(limit?: number): Promise<Activity[]> {
  return apiGet<Activity[]>('/api/activity', { limit });
}

export async function getNodeActivity(nodeId: string): Promise<Activity[]> {
  return apiGet<Activity[]>(`/api/nodes/${nodeId}/activity`);
}
