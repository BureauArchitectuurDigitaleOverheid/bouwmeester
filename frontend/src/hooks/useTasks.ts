import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getTasks, getTask, createTask, updateTask, deleteTask, getUnassignedTasks, getEenheidOverview, getTaskSubtasks, getTasksByPerson } from '@/api/tasks';
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TaskCreate) => createTask(data),
    onError: (error) => {
      console.error('Fout bij aanmaken taak:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });
}

export function useUpdateTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TaskUpdate }) => updateTask(id, data),
    onError: (error) => {
      console.error('Fout bij bijwerken taak:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });
}

export function useDeleteTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteTask(id),
    onError: (error) => {
      console.error('Fout bij verwijderen taak:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
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
