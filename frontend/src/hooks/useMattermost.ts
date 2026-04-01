import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost, apiDelete } from '@/api/client';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

export interface MattermostLinkStatus {
  linked: boolean;
  mattermost_username: string | null;
  bot_dm_url: string | null;
}

export interface MattermostLinkCode {
  code: string;
  expires_at: string;
}

export function useMattermostLinkStatus(poll = false, enabled = true, personId?: string) {
  const params = personId ? `?person_id=${encodeURIComponent(personId)}` : '';
  return useQuery({
    queryKey: queryKeys.mattermost.linkStatus(personId),
    queryFn: () => apiGet<MattermostLinkStatus>(`/api/mattermost/link-status${params}`),
    refetchInterval: poll ? 3000 : false,
    enabled,
  });
}

export function useGenerateLinkCode() {
  return useMutationWithError<MattermostLinkCode, string | undefined>({
    mutationFn: (personId?: string) => {
      const params = personId ? `?person_id=${encodeURIComponent(personId)}` : '';
      return apiPost<MattermostLinkCode>(`/api/mattermost/link-code${params}`);
    },
    errorMessage: 'Fout bij genereren van koppelcode',
  });
}

export function useUnlinkMattermost(personId?: string) {
  return useMutationWithError<unknown, string | undefined>({
    mutationFn: (pid?: string) => {
      const params = pid ? `?person_id=${encodeURIComponent(pid)}` : '';
      return apiDelete(`/api/mattermost/link${params}`);
    },
    errorMessage: 'Fout bij ontkoppelen van Mattermost',
    invalidateKeys: [queryKeys.mattermost.linkStatus(personId)],
  });
}
