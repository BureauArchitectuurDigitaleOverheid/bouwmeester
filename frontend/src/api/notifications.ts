import { apiGet, apiPut } from './client';

export interface Notification {
  id: string;
  person_id: string;
  type: string;
  title: string;
  message?: string;
  is_read: boolean;
  related_node_id?: string;
  related_task_id?: string;
  created_at: string;
}

export interface UnreadCountResponse {
  count: number;
}

export async function getNotifications(
  personId: string,
  unreadOnly = false,
): Promise<Notification[]> {
  return apiGet<Notification[]>('/api/notifications', {
    person_id: personId,
    unread_only: unreadOnly,
  });
}

export async function getUnreadCount(personId: string): Promise<UnreadCountResponse> {
  return apiGet<UnreadCountResponse>('/api/notifications/count', {
    person_id: personId,
  });
}

export async function markNotificationRead(id: string): Promise<Notification> {
  return apiPut<Notification>(`/api/notifications/${id}/read`);
}

export async function markAllNotificationsRead(_personId: string): Promise<{ marked_read: number }> {
  return apiPut<{ marked_read: number }>('/api/notifications/read-all', undefined);
}
