import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createInitiatiefChannelLink,
  createLeadChannelLink,
  deleteChannelLink,
  listInitiatiefChannels,
  listLeadChannels,
  searchMattermostChannels,
  updateChannelLink,
  type MattermostChannelLinkCreate,
  type MattermostChannelLinkUpdate,
} from '@/api/mattermostChannels';
import { queryKeys } from '@/hooks/queryKeys';

export function useInitiatiefChannels(initiatiefId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.initiatieven.mattermostChannels(initiatiefId),
    queryFn: () => listInitiatiefChannels(initiatiefId!),
    enabled: !!initiatiefId,
  });
}

export function useLeadChannels(leadId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.mattermostChannels.forLead(leadId),
    queryFn: () => listLeadChannels(leadId!),
    enabled: !!leadId,
  });
}

export function useSearchMattermostChannels(q: string) {
  return useQuery({
    queryKey: queryKeys.mattermostChannels.search(q),
    queryFn: () => searchMattermostChannels(q),
    enabled: q.length >= 2,
    staleTime: 30_000,
  });
}

export function useCreateInitiatiefChannelLink(initiatiefId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MattermostChannelLinkCreate) =>
      createInitiatiefChannelLink(initiatiefId!, data),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: queryKeys.initiatieven.mattermostChannels(initiatiefId),
      });
    },
  });
}

export function useCreateLeadChannelLink(leadId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MattermostChannelLinkCreate) =>
      createLeadChannelLink(leadId!, data),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: queryKeys.mattermostChannels.forLead(leadId),
      });
    },
  });
}

export function useUpdateChannelLink(
  scope: { type: 'initiatief'; id: string } | { type: 'lead'; id: string } | null,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      linkId,
      data,
    }: {
      linkId: string;
      data: MattermostChannelLinkUpdate;
    }) => updateChannelLink(linkId, data),
    onSuccess: () => {
      if (scope?.type === 'initiatief') {
        qc.invalidateQueries({
          queryKey: queryKeys.initiatieven.mattermostChannels(scope.id),
        });
      } else if (scope?.type === 'lead') {
        qc.invalidateQueries({
          queryKey: queryKeys.mattermostChannels.forLead(scope.id),
        });
      }
    },
  });
}

export function useDeleteChannelLink(
  scope: { type: 'initiatief'; id: string } | { type: 'lead'; id: string } | null,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteChannelLink(linkId),
    onSuccess: () => {
      if (scope?.type === 'initiatief') {
        qc.invalidateQueries({
          queryKey: queryKeys.initiatieven.mattermostChannels(scope.id),
        });
      } else if (scope?.type === 'lead') {
        qc.invalidateQueries({
          queryKey: queryKeys.mattermostChannels.forLead(scope.id),
        });
      }
    },
  });
}
