import { apiGet, apiPost, apiPut } from './client';

export interface Notification {
  id: string;
  person_id: string;
  sender_id?: string;
  sender_name?: string;
  type: string;
  title: string;
  message?: string;
  is_read: boolean;
  related_node_id?: string;
  related_task_id?: string;
  parent_id?: string;
  reply_count: number;
  created_at: string;
}

export interface UnreadCountResponse {
  count: number;
}

export interface DashboardStats {
  corpus_node_count: number;
  open_task_count: number;
  overdue_task_count: number;
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

export async function getNotification(id: string): Promise<Notification> {
  return apiGet<Notification>(`/api/notifications/${id}`);
}

export async function getUnreadCount(personId: string): Promise<UnreadCountResponse> {
  return apiGet<UnreadCountResponse>('/api/notifications/count', {
    person_id: personId,
  });
}

export async function getReplies(notificationId: string): Promise<Notification[]> {
  return apiGet<Notification[]>(`/api/notifications/${notificationId}/replies`);
}

export async function markNotificationRead(id: string): Promise<Notification> {
  return apiPut<Notification>(`/api/notifications/${id}/read`);
}

export async function markAllNotificationsRead(personId: string): Promise<{ marked_read: number }> {
  return apiPut<{ marked_read: number }>(`/api/notifications/read-all?person_id=${personId}`);
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

export async function getDashboardStats(personId: string): Promise<DashboardStats> {
  return apiGet<DashboardStats>('/api/notifications/dashboard-stats', {
    person_id: personId,
  });
}
