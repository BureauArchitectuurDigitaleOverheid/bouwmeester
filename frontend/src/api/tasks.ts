import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Task, TaskCreate, TaskUpdate, TaskStatus, TaskPriority, EenheidOverviewResponse } from '@/types';

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  assignee_id?: string;
  node_id?: string;
  organisatie_eenheid_id?: string;
  include_children?: boolean;
}

export async function getTasks(filters?: TaskFilters): Promise<Task[]> {
  return apiGet<Task[]>('/api/tasks', filters as Record<string, string>);
}

export async function getTask(id: string): Promise<Task> {
  return apiGet<Task>(`/api/tasks/${id}`);
}

export async function createTask(data: TaskCreate): Promise<Task> {
  return apiPost<Task>('/api/tasks', data);
}

export async function updateTask(id: string, data: TaskUpdate): Promise<Task> {
  return apiPut<Task>(`/api/tasks/${id}`, data);
}

export async function deleteTask(id: string): Promise<void> {
  return apiDelete(`/api/tasks/${id}`);
}

export async function getMyTasks(personId: string): Promise<Task[]> {
  return apiGet<Task[]>('/api/tasks', { assignee_id: personId });
}

export async function getUnassignedTasks(organisatieEenheidId?: string): Promise<Task[]> {
  const params: Record<string, string> = {};
  if (organisatieEenheidId) params.organisatie_eenheid_id = organisatieEenheidId;
  return apiGet<Task[]>('/api/tasks/unassigned', params);
}

export async function getEenheidOverview(organisatieEenheidId: string): Promise<EenheidOverviewResponse> {
  return apiGet<EenheidOverviewResponse>('/api/tasks/eenheid-overview', {
    organisatie_eenheid_id: organisatieEenheidId,
  });
}

export async function getTaskSubtasks(taskId: string): Promise<Task[]> {
  return apiGet<Task[]>(`/api/tasks/${taskId}/subtasks`);
}
