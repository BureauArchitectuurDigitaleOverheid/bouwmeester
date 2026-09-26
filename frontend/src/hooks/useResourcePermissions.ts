import { useQuery } from '@tanstack/react-query';
import { apiDelete, apiGet } from '@/api/client';
import { queryKeys } from './queryKeys';
import { useMutationWithError } from './useMutationWithError';

interface ResourcePermissionPerson {
  id: string;
  naam: string;
  email?: string | null;
}

interface ResourcePermission {
  id: string;
  person_id: string;
  person: ResourcePermissionPerson | null;
  resource_type: string;
  resource_id: string;
  rol: string;
  created_at: string;
}

// --- Person-scoped resource permissions (for admin RoleManager) ---

export interface PersonResourcePermission extends ResourcePermission {
  resource_name: string;
}

export function usePersonResourcePermissions(personId: string | null) {
  return useQuery({
    queryKey: queryKeys.admin.personResourcePermissions(personId),
    queryFn: () =>
      apiGet<PersonResourcePermission[]>(`/api/resource-permissions/by-person/${personId}`),
    enabled: !!personId,
  });
}

export function useRemovePersonResourcePermission(personId: string) {
  return useMutationWithError({
    mutationFn: (rpId: string) => apiDelete(`/api/resource-permissions/${rpId}`),
    errorMessage: 'Fout bij verwijderen permissie',
    invalidateKeys: [queryKeys.admin.personResourcePermissions(personId)],
  });
}
