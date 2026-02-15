import { apiGet } from './client';
import type { ActivityFeedResponse, ActivityFeedParams } from '@/types';

export async function getActivityFeed(
  params?: ActivityFeedParams,
): Promise<ActivityFeedResponse> {
  return apiGet<ActivityFeedResponse>('/api/activity/feed', params);
}
