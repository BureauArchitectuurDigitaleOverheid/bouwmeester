import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  sendMessage,
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
    onError: (error) => {
      console.error('Fout bij markeren als gelezen:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (personId: string) => markAllNotificationsRead(personId),
    onError: (error) => {
      console.error('Fout bij markeren notificaties:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: sendMessage,
    onError: (error) => {
      console.error('Fout bij verzenden bericht:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}
