import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type {
  StakeholderAssessment,
  StakeholderAssessmentCreate,
  StakeholderAssessmentUpdate,
  StakeholderScopeType,
} from '@/types';

export async function getStakeholderAssessments(
  scope_type: StakeholderScopeType,
  scope_id: string,
): Promise<StakeholderAssessment[]> {
  return apiGet<StakeholderAssessment[]>('/api/stakeholder-assessments', {
    scope_type,
    scope_id,
  });
}

export async function createStakeholderAssessment(
  data: StakeholderAssessmentCreate,
): Promise<StakeholderAssessment> {
  return apiPost<StakeholderAssessment>('/api/stakeholder-assessments', data);
}

export async function updateStakeholderAssessment(
  id: string,
  data: StakeholderAssessmentUpdate,
): Promise<StakeholderAssessment> {
  return apiPut<StakeholderAssessment>(
    `/api/stakeholder-assessments/${id}`,
    data,
  );
}

export async function deleteStakeholderAssessment(id: string): Promise<void> {
  return apiDelete(`/api/stakeholder-assessments/${id}`);
}
