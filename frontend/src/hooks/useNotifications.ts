import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from '@/api/notifications';

export function useNotifications(personId: string | undefined, unreadOnly = false) {
  return useQuery({
    queryKey: ['notifications', personId, unreadOnly],
    queryFn: () => getNotifications(personId!, unreadOnly),
    enabled: !!personId,
    refetchInterval: 30_000,
  });
}

export function useUnreadCount(personId: string | undefined) {
  return useQuery({
    queryKey: ['notifications', 'count', personId],
    queryFn: () => getUnreadCount(personId!),
    enabled: !!personId,
    refetchInterval: 30_000,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (personId: string) => markAllNotificationsRead(personId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}
