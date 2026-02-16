import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiDelete } from '@/api/client';

export interface MattermostLinkStatus {
  linked: boolean;
  mattermost_username: string | null;
}

export interface MattermostLinkCode {
  code: string;
  expires_at: string;
}

const mattermostKeys = {
  linkStatus: ['mattermost', 'link-status'] as const,
};

export function useMattermostLinkStatus(poll = false) {
  return useQuery({
    queryKey: mattermostKeys.linkStatus,
    queryFn: () => apiGet<MattermostLinkStatus>('/api/mattermost/link-status'),
    refetchInterval: poll ? 3000 : false,
  });
}

export function useGenerateLinkCode() {
  return useMutation({
    mutationFn: () => apiPost<MattermostLinkCode>('/api/mattermost/link-code'),
  });
}

export function useUnlinkMattermost() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete('/api/mattermost/link'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mattermostKeys.linkStatus });
    },
  });
}
