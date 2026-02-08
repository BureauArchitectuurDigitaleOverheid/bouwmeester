import { useQuery } from '@tanstack/react-query';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  sendMessage,
} from '@/api/notifications';
import { useMutationWithError } from '@/hooks/useMutationWithError';

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
  return useMutationWithError({
    mutationFn: (id: string) => markNotificationRead(id),
    errorMessage: 'Fout bij markeren als gelezen',
    invalidateKeys: [['notifications']],
  });
}

export function useMarkAllNotificationsRead() {
  return useMutationWithError({
    mutationFn: (personId: string) => markAllNotificationsRead(personId),
    errorMessage: 'Fout bij markeren notificaties',
    invalidateKeys: [['notifications']],
  });
}

export function useSendMessage() {
  return useMutationWithError({
    mutationFn: sendMessage,
    errorMessage: 'Fout bij verzenden bericht',
    invalidateKeys: [['notifications']],
  });
}
