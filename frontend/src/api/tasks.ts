import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Task, TaskCreate, TaskUpdate, TaskStatus, TaskPriority } from '@/types';

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  assignee_id?: string;
  node_id?: string;
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
