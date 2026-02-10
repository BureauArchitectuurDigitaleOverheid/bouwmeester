import { apiGet } from './client';
import type { ActivityFeedResponse } from '@/types';

export interface ActivityFeedParams {
  [key: string]: string | number | boolean | undefined;
  skip?: number;
  limit?: number;
  event_type?: string;
  actor_id?: string;
}

export async function getActivityFeed(
  params?: ActivityFeedParams,
): Promise<ActivityFeedResponse> {
  return apiGet<ActivityFeedResponse>('/api/activity/feed', params);
}
