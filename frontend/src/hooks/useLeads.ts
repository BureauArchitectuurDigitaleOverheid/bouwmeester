import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebounce } from '@/hooks/useDebounce';
import {
  getLeads,
  getLead,
  createLead,
  updateLead,
  deleteLead,
  moveLead,
  reorderLeads,
  getLeadActivities,
  createLeadActivity,
  deleteLeadActivity,
  addLeadContact,
  removeLeadContact,
  linkLeadNode,
  unlinkLeadNode,
  getLeadMetrics,
  uploadLeadAttachment,
  deleteLeadAttachment,
  addLeadGitHubLink,
  updateLeadGitHubLink,
  deleteLeadGitHubLink,
  refreshLeadGitHubLink,
  parseLeadIntake,
  getCommunityGraph,
  getLeadTimeline,
  getLeadTags,
  addTagToLead,
  removeTagFromLead,
  checkDuplicateLeads,
  mergeLeads,
} from '@/api/leads';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import { useToast } from '@/contexts/ToastContext';
import type {
  Lead,
  LeadCreate,
  LeadUpdate,
  LeadActivityCreate,
  LeadFilters,
} from '@/types';

export function useLeads(filters?: LeadFilters) {
  return useQuery({
    queryKey: queryKeys.leads.list(filters),
    queryFn: () => getLeads(filters),
  });
}

export function useLead(id: string | null) {
  return useQuery({
    queryKey: queryKeys.leads.detail(id),
    queryFn: () => getLead(id!),
    enabled: !!id,
  });
}

export function useCreateLead() {
  return useMutationWithError({
    mutationFn: (data: LeadCreate) => createLead(data),
    errorMessage: 'Fout bij aanmaken lead',
    invalidateKeys: [queryKeys.leads.lists(), queryKeys.leads.metrics()],
  });
}

export function useUpdateLead() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: LeadUpdate }) => updateLead(id, data),
    errorMessage: 'Fout bij bijwerken lead',
    invalidateKeys: [queryKeys.leads.lists(), queryKeys.leads.all, queryKeys.leads.metrics()],
  });
}

export function useDeleteLead() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteLead(id),
    errorMessage: 'Fout bij verwijderen lead',
    invalidateKeys: [queryKeys.leads.lists(), queryKeys.leads.metrics()],
  });
}

export function useMoveLead() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: ({ id, stage }: { id: string; stage: string }) => moveLead(id, stage),
    onMutate: async ({ id, stage }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.leads.lists() });

      const previousLeads = queryClient.getQueriesData<Lead[]>({
        queryKey: queryKeys.leads.lists(),
      });

      queryClient.setQueriesData<Lead[]>(
        { queryKey: queryKeys.leads.lists() },
        (old) => old?.map((lead) => (lead.id === id ? { ...lead, stage: stage as Lead['stage'] } : lead)),
      );

      return { previousLeads };
    },
    onError: (error, _variables, context) => {
      if (context?.previousLeads) {
        for (const [key, data] of context.previousLeads) {
          queryClient.setQueryData(key, data);
        }
      }
      console.error('Fout bij verplaatsen lead:', error);
      showError('Fout bij verplaatsen lead');
    },
    onSettled: (_data, _error, { id }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.leads.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.leads.metrics() });
      // Detail-cache moet ook ververst zodat zichtbaarheidsstatus en andere
      // afgeleide UI (bv. publicatie-badge) klopt met nieuwe stage.
      queryClient.invalidateQueries({ queryKey: queryKeys.leads.detail(id) });
    },
  });
}

export function useReorderLeads() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: ({ leadIds, stage }: { leadIds: string[]; stage: string }) =>
      reorderLeads(leadIds, stage),
    onMutate: async ({ leadIds, stage }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.leads.lists() });

      const previousLeads = queryClient.getQueriesData<Lead[]>({
        queryKey: queryKeys.leads.lists(),
      });

      queryClient.setQueriesData<Lead[]>(
        { queryKey: queryKeys.leads.lists() },
        (old) => {
          if (!old) return old;
          const stageLeads = old.filter((l) => l.stage === stage);
          const otherLeads = old.filter((l) => l.stage !== stage);
          const reordered = leadIds
            .map((id, index) => {
              const lead = stageLeads.find((l) => l.id === id);
              return lead ? { ...lead, sort_order: index } : undefined;
            })
            .filter(Boolean) as Lead[];
          return [...otherLeads, ...reordered];
        },
      );

      return { previousLeads };
    },
    onError: (error, _variables, context) => {
      if (context?.previousLeads) {
        for (const [key, data] of context.previousLeads) {
          queryClient.setQueryData(key, data);
        }
      }
      console.error('Fout bij herordenen leads:', error);
      showError('Fout bij herordenen leads');
    },
    onSettled: (_data, _error, { leadIds }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.leads.lists() });
      // Invalideer details van alle verplaatste leads zodat afgeleide UI
      // (publicatie-status, stage-badge) klopt.
      for (const id of leadIds) {
        queryClient.invalidateQueries({ queryKey: queryKeys.leads.detail(id) });
      }
    },
  });
}

export function useLeadActivities(leadId: string | null) {
  return useQuery({
    queryKey: queryKeys.leads.activities(leadId),
    queryFn: () => getLeadActivities(leadId!),
    enabled: !!leadId,
  });
}

export function useCreateLeadActivity() {
  return useMutationWithError({
    mutationFn: ({ leadId, data }: { leadId: string; data: LeadActivityCreate }) =>
      createLeadActivity(leadId, data),
    errorMessage: 'Fout bij toevoegen activiteit',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useDeleteLeadActivity() {
  return useMutationWithError({
    mutationFn: ({ leadId, activityId }: { leadId: string; activityId: string }) =>
      deleteLeadActivity(leadId, activityId),
    errorMessage: 'Fout bij verwijderen activiteit',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useLeadMetrics() {
  return useQuery({
    queryKey: queryKeys.leads.metrics(),
    queryFn: getLeadMetrics,
  });
}

export function useAddLeadContact() {
  return useMutationWithError({
    mutationFn: ({
      leadId,
      personId,
      rol,
    }: {
      leadId: string;
      personId: string;
      rol: string;
    }) => addLeadContact(leadId, personId, rol),
    errorMessage: 'Fout bij toevoegen externe contactpersoon',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useRemoveLeadContact() {
  return useMutationWithError({
    mutationFn: ({ leadId, contactId }: { leadId: string; contactId: string }) =>
      removeLeadContact(leadId, contactId),
    errorMessage: 'Fout bij verwijderen externe contactpersoon',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useLinkLeadNode() {
  return useMutationWithError({
    mutationFn: ({ leadId, nodeId }: { leadId: string; nodeId: string }) =>
      linkLeadNode(leadId, nodeId),
    errorMessage: 'Fout bij koppelen node',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useUnlinkLeadNode() {
  return useMutationWithError({
    mutationFn: ({ leadId, linkId }: { leadId: string; linkId: string }) =>
      unlinkLeadNode(leadId, linkId),
    errorMessage: 'Fout bij ontkoppelen node',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useUploadLeadAttachment() {
  return useMutationWithError({
    mutationFn: ({ leadId, file }: { leadId: string; file: File }) =>
      uploadLeadAttachment(leadId, file),
    errorMessage: 'Fout bij uploaden bijlage',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useDeleteLeadAttachment() {
  return useMutationWithError({
    mutationFn: ({
      leadId,
      attachmentId,
    }: {
      leadId: string;
      attachmentId: string;
    }) => deleteLeadAttachment(leadId, attachmentId),
    errorMessage: 'Fout bij verwijderen bijlage',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useAddLeadGitHubLink() {
  // Geen useMutationWithError: de form toont een inline error voor 422/409
  // bij ongeldige of dubbele URL. Een toast er bovenop zou dubbel zijn.
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      leadId,
      url,
      title,
    }: {
      leadId: string;
      url: string;
      title?: string | null;
    }) => addLeadGitHubLink(leadId, url, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.leads.all });
    },
  });
}

export function useUpdateLeadGitHubLink() {
  return useMutationWithError({
    mutationFn: ({
      leadId,
      linkId,
      title,
    }: {
      leadId: string;
      linkId: string;
      title: string | null;
    }) => updateLeadGitHubLink(leadId, linkId, title),
    errorMessage: 'Fout bij bewerken GitHub-link',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useDeleteLeadGitHubLink() {
  return useMutationWithError({
    mutationFn: ({
      leadId,
      linkId,
    }: {
      leadId: string;
      linkId: string;
    }) => deleteLeadGitHubLink(leadId, linkId),
    errorMessage: 'Fout bij verwijderen GitHub-link',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useRefreshLeadGitHubLink() {
  return useMutationWithError({
    mutationFn: ({
      leadId,
      linkId,
    }: {
      leadId: string;
      linkId: string;
    }) => refreshLeadGitHubLink(leadId, linkId),
    errorMessage: 'Status verversen mislukt',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useCommunityGraph(initiatiefId?: string) {
  return useQuery({
    queryKey: [...queryKeys.leads.all, 'community-graph', initiatiefId ?? null],
    queryFn: () => getCommunityGraph(initiatiefId),
  });
}

export function useParseLeadIntake() {
  return useMutation({
    mutationFn: ({ rawText, files }: { rawText?: string; files?: File[] }) =>
      parseLeadIntake(rawText, files),
  });
}

export function useLeadTags(leadId: string | null) {
  return useQuery({
    queryKey: queryKeys.tags.forLead(leadId ?? ''),
    queryFn: () => getLeadTags(leadId!),
    enabled: !!leadId,
  });
}

export function useAddTagToLead() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ leadId, data }: { leadId: string; data: { tag_id?: string; tag_name?: string } }) =>
      addTagToLead(leadId, data),
    errorMessage: 'Fout bij toevoegen tag',
    invalidateKeys: [queryKeys.tags.all, queryKeys.leads.all],
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tags.forLead(leadId) });
    },
  });
}

export function useRemoveTagFromLead() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ leadId, tagId }: { leadId: string; tagId: string }) =>
      removeTagFromLead(leadId, tagId),
    errorMessage: 'Fout bij verwijderen tag',
    invalidateKeys: [queryKeys.leads.all],
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tags.forLead(leadId) });
    },
  });
}

export function useCheckDuplicates(title: string, organization?: string) {
  const debouncedTitle = useDebounce(title, 400);
  const debouncedOrg = useDebounce(organization, 400);
  return useQuery({
    queryKey: [...queryKeys.leads.all, 'check-duplicates', debouncedTitle, debouncedOrg],
    queryFn: () => checkDuplicateLeads(debouncedTitle, debouncedOrg),
    enabled: debouncedTitle.length >= 3,
  });
}

export function useMergeLeads() {
  return useMutationWithError({
    mutationFn: ({ sourceId, targetId }: { sourceId: string; targetId: string }) =>
      mergeLeads(sourceId, targetId),
    errorMessage: 'Fout bij samenvoegen leads',
    invalidateKeys: [queryKeys.leads.all],
  });
}

export function useLeadTimeline(params?: {
  stage?: string;
  assignee_id?: string;
  initiatief_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: [...queryKeys.leads.all, 'timeline', params],
    queryFn: () => getLeadTimeline(params),
  });
}
