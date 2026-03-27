import { apiGet, apiPost, apiPut } from './client';
import type { Notification, UnreadCountResponse, DashboardStats } from '@/types';

export async function getNotifications(
  unreadOnly = false,
  devPersonId?: string,
): Promise<Notification[]> {
  const params: Record<string, string> = {};
  if (unreadOnly) params.unread_only = 'true';
  if (devPersonId) params.person_id = devPersonId;
  return apiGet<Notification[]>('/api/notifications', params);
}

export async function getNotification(id: string, devPersonId?: string): Promise<Notification> {
  const params: Record<string, string> = {};
  if (devPersonId) params.person_id = devPersonId;
  return apiGet<Notification>(`/api/notifications/${id}`, params);
}

export async function getUnreadCount(devPersonId?: string): Promise<UnreadCountResponse> {
  const params: Record<string, string> = {};
  if (devPersonId) params.person_id = devPersonId;
  return apiGet<UnreadCountResponse>('/api/notifications/count', params);
}

export async function getReplies(notificationId: string, devPersonId?: string): Promise<Notification[]> {
  const params: Record<string, string> = {};
  if (devPersonId) params.person_id = devPersonId;
  return apiGet<Notification[]>(`/api/notifications/${notificationId}/replies`, params);
}

export async function markNotificationRead(id: string): Promise<Notification> {
  return apiPut<Notification>(`/api/notifications/${id}/read`);
}

export async function markAllNotificationsRead(devPersonId?: string): Promise<{ marked_read: number }> {
  const params = devPersonId ? `?person_id=${encodeURIComponent(devPersonId)}` : '';
  return apiPut<{ marked_read: number }>(`/api/notifications/read-all${params}`);
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

export async function getDashboardStats(devPersonId?: string): Promise<DashboardStats> {
  const params: Record<string, string> = {};
  if (devPersonId) params.person_id = devPersonId;
  return apiGet<DashboardStats>('/api/notifications/dashboard-stats', params);
}
