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
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useAuth } from '@/contexts/AuthContext';

/** Returns the person ID only in dev mode (no OIDC), for the backend fallback param. */
function useDevPersonId(): string | undefined {
  const { oidcConfigured } = useAuth();
  const { currentPerson } = useCurrentPerson();
  return oidcConfigured ? undefined : currentPerson?.id;
}

export function useNotifications(unreadOnly = false) {
  const devPersonId = useDevPersonId();
  const { currentPerson } = useCurrentPerson();
  return useQuery({
    queryKey: queryKeys.notifications.list(unreadOnly),
    queryFn: () => getNotifications(unreadOnly, devPersonId),
    enabled: !!currentPerson,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });
}

export function useNotification(id: string | undefined) {
  const devPersonId = useDevPersonId();
  return useQuery({
    queryKey: queryKeys.notifications.detail(id),
    queryFn: () => getNotification(id!, devPersonId),
    enabled: !!id,
  });
}

export function useUnreadCount() {
  const devPersonId = useDevPersonId();
  const { currentPerson } = useCurrentPerson();
  return useQuery({
    queryKey: queryKeys.notifications.count(),
    queryFn: () => getUnreadCount(devPersonId),
    enabled: !!currentPerson,
    refetchInterval: 30_000,
  });
}

export function useReplies(notificationId: string | undefined) {
  const devPersonId = useDevPersonId();
  return useQuery({
    queryKey: queryKeys.notifications.replies(notificationId),
    queryFn: () => getReplies(notificationId!, devPersonId),
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
  const devPersonId = useDevPersonId();
  return useMutationWithError({
    mutationFn: () => markAllNotificationsRead(devPersonId),
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

export function useDashboardStats() {
  const devPersonId = useDevPersonId();
  const { currentPerson } = useCurrentPerson();
  return useQuery({
    queryKey: queryKeys.dashboardStats(),
    queryFn: () => getDashboardStats(devPersonId),
    enabled: !!currentPerson,
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
