import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createLeadUpdate,
  deleteLeadUpdate,
  editLeadUpdate,
  listLeadUpdates,
  parseLeadUpdate,
  publishLeadUpdate,
  unpublishLeadUpdate,
} from '@/api/leadUpdates';
import type {
  LeadUpdateExtractResult,
  LeadUpdatePost,
  LeadUpdatePostCreate,
  LeadUpdatePostEdit,
} from '@/types';

const queryKey = (leadId: string) => ['leadUpdates', leadId] as const;

export function useLeadUpdates(leadId: string | null) {
  return useQuery<LeadUpdatePost[]>({
    queryKey: queryKey(leadId ?? ''),
    queryFn: () => listLeadUpdates(leadId as string),
    enabled: !!leadId,
  });
}

export function useCreateLeadUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: LeadUpdatePostCreate }) =>
      createLeadUpdate(leadId, data),
    onSuccess: (_post, { leadId }) => {
      qc.invalidateQueries({ queryKey: queryKey(leadId) });
    },
  });
}

export function useEditLeadUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      leadId,
      postId,
      data,
    }: {
      leadId: string;
      postId: string;
      data: LeadUpdatePostEdit;
    }) => editLeadUpdate(leadId, postId, data),
    onSuccess: (_post, { leadId }) => {
      qc.invalidateQueries({ queryKey: queryKey(leadId) });
    },
  });
}

export function usePublishLeadUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, postId }: { leadId: string; postId: string }) =>
      publishLeadUpdate(leadId, postId),
    onSuccess: (_post, { leadId }) => {
      qc.invalidateQueries({ queryKey: queryKey(leadId) });
    },
  });
}

export function useUnpublishLeadUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, postId }: { leadId: string; postId: string }) =>
      unpublishLeadUpdate(leadId, postId),
    onSuccess: (_post, { leadId }) => {
      qc.invalidateQueries({ queryKey: queryKey(leadId) });
    },
  });
}

export function useDeleteLeadUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, postId }: { leadId: string; postId: string }) =>
      deleteLeadUpdate(leadId, postId),
    onSuccess: (_v, { leadId }) => {
      qc.invalidateQueries({ queryKey: queryKey(leadId) });
    },
  });
}

export function useParseLeadUpdate() {
  return useMutation<
    LeadUpdateExtractResult,
    Error,
    {
      leadId: string;
      rawText?: string;
      useLeadHistory?: boolean;
      includeAttachments?: boolean;
      files?: File[];
    }
  >({
    mutationFn: ({ leadId, rawText, useLeadHistory, includeAttachments, files }) =>
      parseLeadUpdate(leadId, { rawText, useLeadHistory, includeAttachments, files }),
  });
}
