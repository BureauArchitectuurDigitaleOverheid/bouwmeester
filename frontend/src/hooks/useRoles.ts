import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost, apiDelete } from '@/api/client';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

export interface RoleDefinition {
  id: string;
  naam: string;
  description: string | null;
  level: string;
  rank: number;
  permissions: string[];
}

export interface PersonRoleAssignment {
  id: string;
  person_id: string;
  person_naam: string | null;
  role_id: string;
  role_naam: string | null;
  organisatie_eenheid_id: string | null;
  organisatie_eenheid_naam: string | null;
  granted_by_id: string | null;
  start_datum: string;
  eind_datum: string | null;
  created_at: string;
}

interface AssignRoleInput {
  person_id: string;
  role_id: string;
  organisatie_eenheid_id?: string;
  start_datum?: string;
  eind_datum?: string;
}

export function useRoles() {
  return useQuery({
    queryKey: queryKeys.admin.roles(),
    queryFn: () => apiGet<RoleDefinition[]>('/api/roles'),
  });
}

export function usePersonRoleAssignments(personId: string | null) {
  return useQuery({
    queryKey: queryKeys.admin.roleAssignments(personId),
    queryFn: () =>
      apiGet<PersonRoleAssignment[]>(
        `/api/roles/persons/${personId}/assignments`,
      ),
    enabled: !!personId,
  });
}

export function useAssignRole() {
  return useMutationWithError({
    mutationFn: (data: AssignRoleInput) =>
      apiPost<PersonRoleAssignment>('/api/roles/assign', data),
    errorMessage: 'Fout bij toewijzen van rol',
    invalidateKeys: [queryKeys.admin.roleAssignmentsAll()],
  });
}

export function useRevokeRole() {
  return useMutationWithError({
    mutationFn: (assignmentId: string) =>
      apiDelete(`/api/roles/assignments/${assignmentId}`),
    errorMessage: 'Fout bij intrekken van rol',
    invalidateKeys: [queryKeys.admin.roleAssignmentsAll()],
  });
}
