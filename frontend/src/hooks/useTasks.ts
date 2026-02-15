import { useQuery } from '@tanstack/react-query';
import { getTasks, getTask, createTask, updateTask, deleteTask, getUnassignedTasks, getEenheidOverview, getTaskSubtasks, getTasksByPerson } from '@/api/tasks';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { TaskCreate, TaskUpdate, TaskFilters } from '@/types';

export function useTasks(filters?: TaskFilters) {
  return useQuery({
    queryKey: queryKeys.tasks.list(filters),
    queryFn: () => getTasks(filters),
  });
}

export function useTask(id: string | null) {
  return useQuery({
    queryKey: queryKeys.tasks.detail(id),
    queryFn: () => getTask(id!),
    enabled: !!id,
  });
}

export function useCreateTask() {
  return useMutationWithError({
    mutationFn: (data: TaskCreate) => createTask(data),
    errorMessage: 'Fout bij aanmaken taak',
    invalidateKeys: [queryKeys.tasks.lists()],
  });
}

export function useUpdateTask() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) => updateTask(id, data),
    errorMessage: 'Fout bij bijwerken taak',
    invalidateKeys: [queryKeys.tasks.lists()],
  });
}

export function useDeleteTask() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteTask(id),
    errorMessage: 'Fout bij verwijderen taak',
    invalidateKeys: [queryKeys.tasks.lists()],
  });
}

export function useUnassignedTasks(organisatieEenheidId?: string) {
  return useQuery({
    queryKey: queryKeys.tasks.unassigned(organisatieEenheidId),
    queryFn: () => getUnassignedTasks(organisatieEenheidId),
  });
}

export function useEenheidOverview(organisatieEenheidId: string | null) {
  return useQuery({
    queryKey: queryKeys.tasks.eenheidOverview(organisatieEenheidId),
    queryFn: () => getEenheidOverview(organisatieEenheidId!),
    enabled: !!organisatieEenheidId,
  });
}

export function useTaskSubtasks(taskId: string | null) {
  return useQuery({
    queryKey: queryKeys.tasks.subtasks(taskId),
    queryFn: () => getTaskSubtasks(taskId!),
    enabled: !!taskId,
  });
}

export function useTasksByPerson(personId: string | null) {
  return useQuery({
    queryKey: queryKeys.tasks.byPerson(personId),
    queryFn: () => getTasksByPerson(personId!),
    enabled: !!personId,
  });
}
