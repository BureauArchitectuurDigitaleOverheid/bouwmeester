import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { getActivityFeed } from '@/api/activity';
import { queryKeys } from '@/hooks/queryKeys';
import type { ActivityFeedParams } from '@/types';

export function useActivityFeed(params?: ActivityFeedParams) {
  return useQuery({
    queryKey: queryKeys.activityFeed(params),
    queryFn: () => getActivityFeed(params),
    placeholderData: keepPreviousData,
  });
}
