import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost, apiDelete } from '@/api/client';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

export interface MattermostLinkStatus {
  linked: boolean;
  mattermost_username: string | null;
}

export interface MattermostLinkCode {
  code: string;
  expires_at: string;
}

export function useMattermostLinkStatus(poll = false, enabled = true) {
  return useQuery({
    queryKey: queryKeys.mattermost.linkStatus,
    queryFn: () => apiGet<MattermostLinkStatus>('/api/mattermost/link-status'),
    refetchInterval: poll ? 3000 : false,
    enabled,
  });
}

export function useGenerateLinkCode() {
  return useMutationWithError<MattermostLinkCode>({
    mutationFn: () => apiPost<MattermostLinkCode>('/api/mattermost/link-code'),
    errorMessage: 'Fout bij genereren van koppelcode',
  });
}

export function useUnlinkMattermost() {
  return useMutationWithError({
    mutationFn: () => apiDelete('/api/mattermost/link'),
    errorMessage: 'Fout bij ontkoppelen van Mattermost',
    invalidateKeys: [queryKeys.mattermost.linkStatus],
  });
}
