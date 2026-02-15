import { apiGet, apiPost, apiPut } from './client';
import type { Notification, UnreadCountResponse, DashboardStats } from '@/types';

export async function getNotifications(
  personId: string,
  unreadOnly = false,
): Promise<Notification[]> {
  return apiGet<Notification[]>('/api/notifications', {
    person_id: personId,
    unread_only: unreadOnly,
  });
}

export async function getNotification(id: string, personId?: string): Promise<Notification> {
  const params: Record<string, string> = {};
  if (personId) params.person_id = personId;
  return apiGet<Notification>(`/api/notifications/${id}`, params);
}

export async function getUnreadCount(personId: string): Promise<UnreadCountResponse> {
  return apiGet<UnreadCountResponse>('/api/notifications/count', {
    person_id: personId,
  });
}

export async function getReplies(notificationId: string, personId?: string): Promise<Notification[]> {
  const params: Record<string, string> = {};
  if (personId) params.person_id = personId;
  return apiGet<Notification[]>(`/api/notifications/${notificationId}/replies`, params);
}

export async function markNotificationRead(id: string): Promise<Notification> {
  return apiPut<Notification>(`/api/notifications/${id}/read`);
}

export async function markAllNotificationsRead(personId: string): Promise<{ marked_read: number }> {
  return apiPut<{ marked_read: number }>(`/api/notifications/read-all?person_id=${encodeURIComponent(personId)}`);
}

export async function sendMessage(data: {
  person_id: string;
  sender_id: string;
  message: string;
}): Promise<Notification> {
  return apiPost<Notification>('/api/notifications/send', data);
}

export async function replyToNotification(
  notificationId: string,
  data: { sender_id: string; message: string },
): Promise<Notification> {
  return apiPost<Notification>(`/api/notifications/${notificationId}/reply`, data);
}

export async function reactToMessage(
  notificationId: string,
  data: { sender_id: string; emoji: string },
): Promise<{ action: string }> {
  return apiPost<{ action: string }>(`/api/notifications/${notificationId}/react`, data);
}

export async function getDashboardStats(personId: string): Promise<DashboardStats> {
  return apiGet<DashboardStats>('/api/notifications/dashboard-stats', {
    person_id: personId,
  });
}
