import { useQuery } from '@tanstack/react-query';
import {
  getNotifications,
  getNotification,
  getUnreadCount,
  getReplies,
  markNotificationRead,
  markAllNotificationsRead,
  sendMessage,
  replyToNotification,
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

export function useNotification(id: string | undefined) {
  return useQuery({
    queryKey: ['notifications', 'detail', id],
    queryFn: () => getNotification(id!),
    enabled: !!id,
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

export function useReplies(notificationId: string | undefined) {
  return useQuery({
    queryKey: ['notifications', 'replies', notificationId],
    queryFn: () => getReplies(notificationId!),
    enabled: !!notificationId,
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

export function useReplyToNotification() {
  return useMutationWithError({
    mutationFn: ({ notificationId, data }: { notificationId: string; data: { sender_id: string; message: string } }) =>
      replyToNotification(notificationId, data),
    errorMessage: 'Fout bij verzenden reactie',
    invalidateKeys: [['notifications']],
  });
}
