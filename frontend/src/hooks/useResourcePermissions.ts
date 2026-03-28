import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client';

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

export function useResourcePermissions(resourceType: string, resourceId: string | undefined) {
  return useQuery({
    queryKey: ['resource-permissions', resourceType, resourceId],
    queryFn: () => apiGet<ResourcePermission[]>(`/api/resource-permissions/${resourceType}/${resourceId}`),
    enabled: !!resourceId,
  });
}

export function useAddResourcePermission(resourceType: string, resourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { person_id: string; rol: string }) =>
      apiPost<ResourcePermission>(`/api/resource-permissions/${resourceType}/${resourceId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resource-permissions', resourceType, resourceId] });
    },
  });
}

export function useUpdateResourcePermission(resourceType: string, resourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ rpId, rol }: { rpId: string; rol: string }) =>
      apiPut<ResourcePermission>(`/api/resource-permissions/${rpId}`, { rol }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resource-permissions', resourceType, resourceId] });
    },
  });
}

export function useRemoveResourcePermission(resourceType: string, resourceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (rpId: string) => apiDelete(`/api/resource-permissions/${rpId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resource-permissions', resourceType, resourceId] });
    },
  });
}
