import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { getActivityFeed } from '@/api/activity';
import type { ActivityFeedParams } from '@/types';

export function useActivityFeed(params?: ActivityFeedParams) {
  return useQuery({
    queryKey: ['activity-feed', params],
    queryFn: () => getActivityFeed(params),
    placeholderData: keepPreviousData,
  });
}
