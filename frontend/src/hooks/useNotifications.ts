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
  reactToMessage,
  getDashboardStats,
} from '@/api/notifications';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

export function useNotifications(personId: string | undefined, unreadOnly = false) {
  return useQuery({
    queryKey: queryKeys.notifications.list(personId, unreadOnly),
    queryFn: () => getNotifications(personId!, unreadOnly),
    enabled: !!personId,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });
}

export function useNotification(id: string | undefined, personId?: string) {
  return useQuery({
    queryKey: queryKeys.notifications.detail(id, personId),
    queryFn: () => getNotification(id!, personId),
    enabled: !!id,
  });
}

export function useUnreadCount(personId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.notifications.count(personId),
    queryFn: () => getUnreadCount(personId!),
    enabled: !!personId,
    refetchInterval: 30_000,
  });
}

export function useReplies(notificationId: string | undefined, personId?: string) {
  return useQuery({
    queryKey: queryKeys.notifications.replies(notificationId, personId),
    queryFn: () => getReplies(notificationId!, personId),
    enabled: !!notificationId,
    refetchInterval: 5_000,
  });
}

export function useMarkNotificationRead() {
  return useMutationWithError({
    mutationFn: (id: string) => markNotificationRead(id),
    errorMessage: 'Fout bij markeren als gelezen',
    invalidateKeys: [queryKeys.notifications.all],
  });
}

export function useMarkAllNotificationsRead() {
  return useMutationWithError({
    mutationFn: (personId: string) => markAllNotificationsRead(personId),
    errorMessage: 'Fout bij markeren notificaties',
    invalidateKeys: [queryKeys.notifications.all],
  });
}

export function useSendMessage() {
  return useMutationWithError({
    mutationFn: sendMessage,
    errorMessage: 'Fout bij verzenden bericht',
    invalidateKeys: [queryKeys.notifications.all],
  });
}

export function useDashboardStats(personId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.dashboardStats(personId),
    queryFn: () => getDashboardStats(personId!),
    enabled: !!personId,
    refetchInterval: 60_000,
  });
}

export function useReactToMessage() {
  return useMutationWithError({
    mutationFn: ({ notificationId, data }: { notificationId: string; data: { sender_id: string; emoji: string } }) =>
      reactToMessage(notificationId, data),
    errorMessage: 'Fout bij emoji-reactie',
    invalidateKeys: [queryKeys.notifications.all],
  });
}

export function useReplyToNotification() {
  return useMutationWithError({
    mutationFn: ({ notificationId, data }: { notificationId: string; data: { sender_id: string; message: string } }) =>
      replyToNotification(notificationId, data),
    errorMessage: 'Fout bij verzenden reactie',
    invalidateKeys: [queryKeys.notifications.all],
  });
}
