import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Check, CheckCheck } from 'lucide-react';
import { useNotifications, useUnreadCount, useMarkNotificationRead, useMarkAllNotificationsRead } from '@/hooks/useNotifications';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import type { Notification } from '@/api/notifications';
import { richTextToPlain } from '@/utils/richtext';

interface NotificationBellProps {
  personId: string | undefined;
}

function timeAgo(dateStr: string): string {
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now.getTime() - then.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'Zojuist';
  if (diffMin < 60) return `${diffMin}m geleden`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}u geleden`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays}d geleden`;
}

const TYPE_COLORS: Record<string, string> = {
  task_assigned: 'bg-blue-100 text-blue-700',
  task_overdue: 'bg-red-100 text-red-700',
  node_updated: 'bg-green-100 text-green-700',
  edge_created: 'bg-purple-100 text-purple-700',
  coverage_needed: 'bg-amber-100 text-amber-700',
  direct_message: 'bg-green-100 text-green-700',
  agent_prompt: 'bg-violet-100 text-violet-700',
  mention: 'bg-cyan-100 text-cyan-700',
};

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
              TYPE_COLORS[notification.type] || 'bg-gray-100 text-gray-700'
            }`}
          >
            {notification.type.replace(/_/g, ' ')}
          </span>
          <span className="text-xs text-text-secondary">{timeAgo(notification.created_at)}</span>
        </div>
        <p className="text-sm font-medium text-text truncate">{notification.title}</p>
        {notification.message && (
          <p className="text-xs text-text-secondary truncate mt-0.5">{richTextToPlain(notification.message)}</p>
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
        className="relative flex items-center justify-center h-8 w-8 rounded-full text-text-secondary hover:bg-gray-100 hover:text-text transition-colors"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center h-4 min-w-[16px] rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 z-50 w-80 max-h-96 rounded-xl border border-border bg-surface shadow-xl overflow-hidden">
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
                    if (!notification.is_read) markRead.mutate(notification.id);
                    setOpen(false);
                    if (notification.related_task_id) {
                      openTaskDetail(notification.related_task_id);
                    } else if (notification.related_node_id) {
                      openNodeDetail(notification.related_node_id);
                    } else {
                      navigate(`/?notification=${notification.id}`);
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
    </div>
  );
}
