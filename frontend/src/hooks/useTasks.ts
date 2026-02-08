import { useQuery } from '@tanstack/react-query';
import { getTasks, getTask, createTask, updateTask, deleteTask, getUnassignedTasks, getEenheidOverview, getTaskSubtasks, getTasksByPerson } from '@/api/tasks';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { TaskCreate, TaskUpdate } from '@/types';
import type { TaskFilters } from '@/api/tasks';

export function useTasks(filters?: TaskFilters) {
  return useQuery({
    queryKey: ['tasks', filters],
    queryFn: () => getTasks(filters),
  });
}

export function useTask(id: string | null) {
  return useQuery({
    queryKey: ['tasks', id],
    queryFn: () => getTask(id!),
    enabled: !!id,
  });
}

export function useCreateTask() {
  return useMutationWithError({
    mutationFn: (data: TaskCreate) => createTask(data),
    errorMessage: 'Fout bij aanmaken taak',
    invalidateKeys: [['tasks']],
  });
}

export function useUpdateTask() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) => updateTask(id, data),
    errorMessage: 'Fout bij bijwerken taak',
    invalidateKeys: [['tasks']],
  });
}

export function useDeleteTask() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteTask(id),
    errorMessage: 'Fout bij verwijderen taak',
    invalidateKeys: [['tasks']],
  });
}

export function useUnassignedTasks(organisatieEenheidId?: string) {
  return useQuery({
    queryKey: ['tasks', 'unassigned', organisatieEenheidId],
    queryFn: () => getUnassignedTasks(organisatieEenheidId),
  });
}

export function useEenheidOverview(organisatieEenheidId: string | null) {
  return useQuery({
    queryKey: ['tasks', 'eenheid-overview', organisatieEenheidId],
    queryFn: () => getEenheidOverview(organisatieEenheidId!),
    enabled: !!organisatieEenheidId,
  });
}

export function useTaskSubtasks(taskId: string | null) {
  return useQuery({
    queryKey: ['tasks', taskId, 'subtasks'],
    queryFn: () => getTaskSubtasks(taskId!),
    enabled: !!taskId,
  });
}

export function useTasksByPerson(personId: string | null) {
  return useQuery({
    queryKey: ['tasks', 'by-person', personId],
    queryFn: () => getTasksByPerson(personId!),
    enabled: !!personId,
  });
}
