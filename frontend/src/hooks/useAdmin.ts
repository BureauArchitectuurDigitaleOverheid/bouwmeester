import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '@/api/client';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { AccessRequest } from '@/types';

export interface WhitelistEmail {
  id: string;
  email: string;
  added_by: string | null;
  created_at: string;
}

export function useWhitelist() {
  return useQuery({
    queryKey: queryKeys.admin.whitelist(),
    queryFn: () => apiGet<WhitelistEmail[]>('/api/admin/whitelist'),
  });
}

export function useAddWhitelistEmail() {
  return useMutationWithError({
    mutationFn: (email: string) =>
      apiPost<WhitelistEmail>('/api/admin/whitelist', { email }),
    errorMessage: 'Fout bij toevoegen van e-mailadres',
    invalidateKeys: [queryKeys.admin.whitelist()],
  });
}

export function useRemoveWhitelistEmail() {
  return useMutationWithError({
    mutationFn: (id: string) => apiDelete(`/api/admin/whitelist/${id}`),
    errorMessage: 'Fout bij verwijderen van e-mailadres',
    invalidateKeys: [queryKeys.admin.whitelist()],
  });
}

export function useAccessRequests(status?: string) {
  return useQuery({
    queryKey: queryKeys.admin.accessRequests(status),
    queryFn: () =>
      apiGet<AccessRequest[]>('/api/admin/access-requests', status ? { status } : undefined),
  });
}

export function useReviewAccessRequest() {
  return useMutationWithError({
    mutationFn: ({ id, action, deny_reason }: { id: string; action: 'approve' | 'deny'; deny_reason?: string }) =>
      apiPatch<AccessRequest>(`/api/admin/access-requests/${id}`, { action, deny_reason }),
    errorMessage: 'Fout bij beoordelen van toegangsverzoek',
    invalidateKeys: [queryKeys.admin.accessRequestsAll(), queryKeys.admin.whitelist()],
  });
}

// ---------------------------------------------------------------------------
// App configuration (LLM keys, model settings)
// ---------------------------------------------------------------------------

export interface AppConfigEntry {
  id: string;
  key: string;
  value: string;
  description: string | null;
  is_secret: boolean;
  updated_by: string | null;
  updated_at: string;
  created_at: string;
}

export function useAppConfig() {
  return useQuery({
    queryKey: queryKeys.admin.config(),
    queryFn: () => apiGet<AppConfigEntry[]>('/api/admin/config'),
  });
}

export function useUpdateAppConfig() {
  return useMutationWithError({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      apiPatch<AppConfigEntry>(`/api/admin/config/${key}`, { value }),
    errorMessage: 'Fout bij opslaan van configuratie',
    invalidateKeys: [queryKeys.admin.config()],
  });
}
