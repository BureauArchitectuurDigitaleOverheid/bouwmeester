import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Check, CheckCheck } from 'lucide-react';
import { useNotifications, useUnreadCount, useMarkNotificationRead, useMarkAllNotificationsRead } from '@/hooks/useNotifications';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { timeAgo } from '@/utils/dates';
import type { Notification } from '@/api/notifications';
import { richTextToPlain } from '@/utils/richtext';
import { MessageThread } from '@/components/inbox/MessageThread';
import { NOTIFICATION_TYPE_COLORS, NOTIFICATION_TYPE_LABELS } from '@/types';

interface NotificationBellProps {
  personId: string | undefined;
}

function NotificationItem({
  notification,
  onMarkRead,
  onClick,
}: {
  notification: Notification;
  onMarkRead: (id: string) => void;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors ${
        !notification.is_read ? 'bg-blue-50/50' : ''
      } ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span
            className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
              NOTIFICATION_TYPE_COLORS[notification.type] || 'bg-gray-100 text-gray-700'
            }`}
          >
            {NOTIFICATION_TYPE_LABELS[notification.type] || notification.type.replace(/_/g, ' ')}
          </span>
          <span className="text-xs text-text-secondary">{timeAgo(notification.last_activity_at ?? notification.created_at)}</span>
        </div>
        <p className="text-sm font-medium text-text truncate">{notification.title}</p>
        {(notification.last_message || notification.message) && (
          <p className="text-xs text-text-secondary truncate mt-0.5">{richTextToPlain(notification.last_message ?? notification.message ?? '')}</p>
        )}
      </div>
      {!notification.is_read && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onMarkRead(notification.id);
          }}
          className="shrink-0 rounded p-1 text-text-secondary hover:bg-gray-200 hover:text-text transition-colors"
          title="Markeer als gelezen"
        >
          <Check className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export function NotificationBell({ personId }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();

  const { data: countData } = useUnreadCount(personId);
  const { data: notifications } = useNotifications(personId, false);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const unreadCount = countData?.count ?? 0;

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!personId) return null;

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center justify-center h-10 w-10 md:h-8 md:w-8 rounded-full text-text-secondary hover:bg-gray-100 hover:text-text transition-colors"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center h-4 min-w-[16px] rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-x-2 top-16 z-50 sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 w-auto sm:w-80 max-h-96 rounded-xl border border-border bg-surface shadow-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h3 className="text-sm font-semibold text-text">Meldingen</h3>
            {unreadCount > 0 && (
              <button
                onClick={() => markAllRead.mutate(personId)}
                className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 transition-colors"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Alles gelezen
              </button>
            )}
          </div>

          {/* Notification list */}
          <div className="overflow-y-auto max-h-72 divide-y divide-border">
            {notifications && notifications.length > 0 ? (
              notifications.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onMarkRead={(id) => markRead.mutate(id)}
                  onClick={() => {
                    if (notification.type === 'access_request') {
                      navigate('/admin?tab=requests');
                      if (!notification.is_read) markRead.mutate(notification.id);
                      setOpen(false);
                    } else if (notification.type === 'direct_message' || notification.type === 'agent_prompt') {
                      setThreadId(notification.id);
                      setOpen(false);
                    } else if (notification.related_task_id) {
                      openTaskDetail(notification.related_task_id);
                      if (!notification.is_read) markRead.mutate(notification.id);
                      setOpen(false);
                    } else if (notification.related_node_id) {
                      openNodeDetail(notification.related_node_id);
                      if (!notification.is_read) markRead.mutate(notification.id);
                      setOpen(false);
                    }
                  }}
                />
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-text-secondary">
                <Bell className="h-8 w-8 mb-2 opacity-30" />
                <p className="text-sm">Geen meldingen</p>
              </div>
            )}
          </div>
        </div>
      )}

      {threadId && (
        <MessageThread notificationId={threadId} onClose={() => setThreadId(null)} />
      )}
    </div>
  );
}
