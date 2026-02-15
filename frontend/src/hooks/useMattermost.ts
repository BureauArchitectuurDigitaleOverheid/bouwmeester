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

export function useMattermostLinkStatus(personId?: string | null, poll = false) {
  const params = personId ? { person_id: personId } : {};
  return useQuery({
    queryKey: [...mattermostKeys.linkStatus, personId],
    queryFn: () => apiGet<MattermostLinkStatus>('/api/mattermost/link-status', params),
    enabled: !!personId,
    refetchInterval: poll ? 3000 : false,
  });
}

export function useGenerateLinkCode(personId?: string | null) {
  const params = personId ? `?person_id=${personId}` : '';
  return useMutation({
    mutationFn: () => apiPost<MattermostLinkCode>(`/api/mattermost/link-code${params}`),
  });
}

export function useUnlinkMattermost(personId?: string | null) {
  const queryClient = useQueryClient();
  const params = personId ? `?person_id=${personId}` : '';
  return useMutation({
    mutationFn: () => apiDelete(`/api/mattermost/link${params}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mattermostKeys.linkStatus });
    },
  });
}
