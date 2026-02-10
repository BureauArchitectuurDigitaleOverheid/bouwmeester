import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { getActivityFeed, type ActivityFeedParams } from '@/api/activity';

export function useActivityFeed(params?: ActivityFeedParams) {
  return useQuery({
    queryKey: ['activity-feed', params],
    queryFn: () => getActivityFeed(params),
    placeholderData: keepPreviousData,
  });
}
