import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch, apiDelete } from '@/api/client';
import { useMutationWithError } from '@/hooks/useMutationWithError';

export interface WhitelistEmail {
  id: string;
  email: string;
  added_by: string | null;
  created_at: string;
}

export interface AdminUser {
  id: string;
  naam: string;
  email: string | null;
  functie: string | null;
  is_admin: boolean;
  is_active: boolean;
}

export function useWhitelist() {
  return useQuery({
    queryKey: ['admin', 'whitelist'],
    queryFn: () => apiGet<WhitelistEmail[]>('/api/admin/whitelist'),
  });
}

export function useAddWhitelistEmail() {
  return useMutationWithError({
    mutationFn: (email: string) =>
      apiPost<WhitelistEmail>('/api/admin/whitelist', { email }),
    errorMessage: 'Fout bij toevoegen van e-mailadres',
    invalidateKeys: [['admin', 'whitelist']],
  });
}

export function useRemoveWhitelistEmail() {
  return useMutationWithError({
    mutationFn: (id: string) => apiDelete(`/api/admin/whitelist/${id}`),
    errorMessage: 'Fout bij verwijderen van e-mailadres',
    invalidateKeys: [['admin', 'whitelist']],
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => apiGet<AdminUser[]>('/api/admin/users'),
  });
}

export function useToggleAdmin() {
  return useMutationWithError({
    mutationFn: ({ id, is_admin }: { id: string; is_admin: boolean }) =>
      apiPatch<AdminUser>(`/api/admin/users/${id}`, { is_admin }),
    errorMessage: 'Fout bij wijzigen van admin-status',
    invalidateKeys: [['admin', 'users']],
  });
}
