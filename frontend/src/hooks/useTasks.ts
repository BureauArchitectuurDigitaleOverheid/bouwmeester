import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getTasks, getTask, createTask, updateTask, deleteTask, getUnassignedTasks, getEenheidOverview, getTaskSubtasks, getTasksByPerson, reorderSubtasks, getWorkTypes, getTasksByOpdracht } from '@/api/tasks';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import { useToast } from '@/contexts/ToastContext';
import type { Task, TaskCreate, TaskUpdate, TaskFilters } from '@/types';

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
    invalidateKeys: [queryKeys.tasks.lists(), queryKeys.tasks.workTypes()],
  });
}

export function useUpdateTask() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) => updateTask(id, data),
    errorMessage: 'Fout bij bijwerken taak',
    invalidateKeys: [queryKeys.tasks.lists(), queryKeys.tasks.workTypes()],
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

export function useTasksByOpdracht(opdrachtId: string | null) {
  return useQuery({
    queryKey: queryKeys.tasks.byOpdracht(opdrachtId),
    queryFn: () => getTasksByOpdracht(opdrachtId!),
    enabled: !!opdrachtId,
  });
}

export function useWorkTypes() {
  return useQuery({
    queryKey: queryKeys.tasks.workTypes(),
    queryFn: getWorkTypes,
  });
}

export function useReorderSubtasks() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: ({ taskId, taskIds }: { taskId: string; taskIds: string[] }) =>
      reorderSubtasks(taskId, taskIds),
    onMutate: async ({ taskId, taskIds }) => {
      // Cancel outgoing refetches so they don't overwrite optimistic update
      await queryClient.cancelQueries({ queryKey: queryKeys.tasks.detail(taskId) });

      const previousTask = queryClient.getQueryData<Task>(queryKeys.tasks.detail(taskId));

      if (previousTask?.subtasks) {
        const subtaskMap = new Map(previousTask.subtasks.map((s) => [s.id, s]));
        const reorderedSubtasks = taskIds
          .map((id) => subtaskMap.get(id))
          .filter(Boolean);

        queryClient.setQueryData(queryKeys.tasks.detail(taskId), {
          ...previousTask,
          subtasks: reorderedSubtasks,
        });
      }

      return { previousTask, taskId };
    },
    onError: (error, _variables, context) => {
      // Roll back to previous state
      if (context?.previousTask) {
        queryClient.setQueryData(
          queryKeys.tasks.detail(context.taskId),
          context.previousTask,
        );
      }
      console.error('Fout bij herordenen subtaken:', error);
      showError('Fout bij herordenen subtaken');
    },
    onSettled: (_data, _error, variables) => {
      // Refetch to ensure server state is authoritative
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(variables.taskId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.lists() });
    },
  });
}
