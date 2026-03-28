import { useQuery } from '@tanstack/react-query';
import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client';
import { useMutationWithError } from './useMutationWithError';

interface ResourcePermissionPerson {
  id: string;
  naam: string;
  email?: string | null;
}

export interface ResourcePermission {
  id: string;
  person_id: string;
  person: ResourcePermissionPerson | null;
  resource_type: string;
  resource_id: string;
  rol: string;
  created_at: string;
}

const rpKeys = {
  list: (resourceType: string, resourceId: string | undefined) =>
    ['resource-permissions', resourceType, resourceId] as const,
};

export function useResourcePermissions(resourceType: string, resourceId: string | undefined) {
  return useQuery({
    queryKey: rpKeys.list(resourceType, resourceId),
    queryFn: () => apiGet<ResourcePermission[]>(`/api/resource-permissions/${resourceType}/${resourceId}`),
    enabled: !!resourceId,
  });
}

export function useAddResourcePermission(resourceType: string, resourceId: string) {
  return useMutationWithError({
    mutationFn: (data: { person_id: string; rol: string }) =>
      apiPost<ResourcePermission>(`/api/resource-permissions/${resourceType}/${resourceId}`, data),
    errorMessage: 'Fout bij toevoegen permissie',
    invalidateKeys: [rpKeys.list(resourceType, resourceId)],
  });
}

export function useUpdateResourcePermission(resourceType: string, resourceId: string) {
  return useMutationWithError({
    mutationFn: ({ rpId, rol }: { rpId: string; rol: string }) =>
      apiPut<ResourcePermission>(`/api/resource-permissions/${rpId}`, { rol }),
    errorMessage: 'Fout bij wijzigen permissie',
    invalidateKeys: [rpKeys.list(resourceType, resourceId)],
  });
}

export function useRemoveResourcePermission(resourceType: string, resourceId: string) {
  return useMutationWithError({
    mutationFn: (rpId: string) => apiDelete(`/api/resource-permissions/${rpId}`),
    errorMessage: 'Fout bij verwijderen permissie',
    invalidateKeys: [rpKeys.list(resourceType, resourceId)],
  });
}
