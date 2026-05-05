import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getStakeholderAssessments,
  createStakeholderAssessment,
  updateStakeholderAssessment,
  deleteStakeholderAssessment,
} from '@/api/stakeholderAssessments';
import type {
  StakeholderAssessmentCreate,
  StakeholderAssessmentUpdate,
  StakeholderScopeType,
} from '@/types';

const key = (scopeType: StakeholderScopeType, scopeId: string) =>
  ['stakeholder-assessments', scopeType, scopeId] as const;

export function useStakeholderAssessments(
  scopeType: StakeholderScopeType,
  scopeId: string | undefined,
) {
  return useQuery({
    queryKey: key(scopeType, scopeId ?? ''),
    queryFn: () => getStakeholderAssessments(scopeType, scopeId!),
    enabled: !!scopeId,
  });
}

export function useCreateStakeholderAssessment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: StakeholderAssessmentCreate) =>
      createStakeholderAssessment(data),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: key(vars.scope_type, vars.scope_id) });
    },
  });
}

export function useUpdateStakeholderAssessment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: StakeholderAssessmentUpdate;
      scopeType: StakeholderScopeType;
      scopeId: string;
    }) => updateStakeholderAssessment(id, data),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: key(vars.scopeType, vars.scopeId) });
    },
  });
}

export function useDeleteStakeholderAssessment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
    }: {
      id: string;
      scopeType: StakeholderScopeType;
      scopeId: string;
    }) => deleteStakeholderAssessment(id),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: key(vars.scopeType, vars.scopeId) });
    },
  });
}
