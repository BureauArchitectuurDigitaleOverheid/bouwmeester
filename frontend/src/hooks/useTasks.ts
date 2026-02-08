import { useQuery } from '@tanstack/react-query';
import { getTasks, getTask, createTask, updateTask, deleteTask, getUnassignedTasks, getEenheidOverview, getTaskSubtasks, getTasksByPerson } from '@/api/tasks';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { TaskCreate, TaskUpdate } from '@/types';
import type { TaskFilters } from '@/api/tasks';

export function useTasks(filters?: TaskFilters) {
  return useQuery({
    queryKey: ['tasks', 'list', filters],
    queryFn: () => getTasks(filters),
  });
}

export function useTask(id: string | null) {
  return useQuery({
    queryKey: ['tasks', 'detail', id],
    queryFn: () => getTask(id!),
    enabled: !!id,
  });
}

export function useCreateTask() {
  return useMutationWithError({
    mutationFn: (data: TaskCreate) => createTask(data),
    errorMessage: 'Fout bij aanmaken taak',
    invalidateKeys: [['tasks', 'list']],
  });
}

export function useUpdateTask() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) => updateTask(id, data),
    errorMessage: 'Fout bij bijwerken taak',
    invalidateKeys: [['tasks', 'list']],
  });
}

export function useDeleteTask() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteTask(id),
    errorMessage: 'Fout bij verwijderen taak',
    invalidateKeys: [['tasks', 'list']],
  });
}

export function useUnassignedTasks(organisatieEenheidId?: string) {
  return useQuery({
    queryKey: ['tasks', 'list', 'unassigned', organisatieEenheidId],
    queryFn: () => getUnassignedTasks(organisatieEenheidId),
  });
}

export function useEenheidOverview(organisatieEenheidId: string | null) {
  return useQuery({
    queryKey: ['tasks', 'list', 'eenheid-overview', organisatieEenheidId],
    queryFn: () => getEenheidOverview(organisatieEenheidId!),
    enabled: !!organisatieEenheidId,
  });
}

export function useTaskSubtasks(taskId: string | null) {
  return useQuery({
    queryKey: ['tasks', 'detail', taskId, 'subtasks'],
    queryFn: () => getTaskSubtasks(taskId!),
    enabled: !!taskId,
  });
}

export function useTasksByPerson(personId: string | null) {
  return useQuery({
    queryKey: ['tasks', 'list', 'by-person', personId],
    queryFn: () => getTasksByPerson(personId!),
    enabled: !!personId,
  });
}
