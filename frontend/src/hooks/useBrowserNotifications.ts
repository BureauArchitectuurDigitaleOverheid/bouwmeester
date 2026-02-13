import { useEffect, useRef } from 'react';
import { useNotifications } from '@/hooks/useNotifications';
import { richTextToPlain } from '@/utils/richtext';
import { NOTIFICATION_TYPE_LABELS, titleCase } from '@/types';

const STORAGE_KEY = 'browser-notifications-enabled';

// --- localStorage helpers ---

export function isBrowserNotificationsEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function setBrowserNotificationsEnabled(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(enabled));
  } catch {
    // storage unavailable
  }
}

// --- Permission helper ---

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) return 'denied';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  return Notification.requestPermission();
}

// --- Hook ---

export function useBrowserNotifications(personId: string | undefined): void {
  const { data: notifications } = useNotifications(personId, false);
  const seenIdsRef = useRef<Set<string> | null>(null);
  const prevPersonIdRef = useRef<string | undefined>(personId);

  useEffect(() => {
    // Reset tracking when personId changes
    if (prevPersonIdRef.current !== personId) {
      seenIdsRef.current = null;
      prevPersonIdRef.current = personId;
    }

    if (!notifications || !personId) return;

    const unreadIds = new Set(
      notifications.filter((n) => !n.is_read).map((n) => n.id),
    );

    // First load: seed without firing
    if (seenIdsRef.current === null) {
      seenIdsRef.current = unreadIds;
      return;
    }

    // Guard: user must have opted in, permission must be granted, tab not visible
    if (
      !isBrowserNotificationsEnabled() ||
      !('Notification' in window) ||
      Notification.permission !== 'granted' ||
      document.visibilityState === 'visible'
    ) {
      // Still update tracking so we don't fire stale notifications later
      seenIdsRef.current = unreadIds;
      return;
    }

    // Find genuinely new unread IDs
    for (const id of unreadIds) {
      if (!seenIdsRef.current.has(id)) {
        const notification = notifications.find((n) => n.id === id);
        if (notification) {
          const typeLabel =
            NOTIFICATION_TYPE_LABELS[notification.type] ??
            titleCase(notification.type.replace(/_/g, ' '));
          const body = richTextToPlain(
            notification.last_message ?? notification.message ?? '',
          );

          const n = new Notification(notification.title, {
            body: body ? `${typeLabel} — ${body}` : typeLabel,
            tag: notification.id, // deduplicates
          });
          n.onclick = () => {
            window.focus();
            n.close();
          };
        }
      }
    }

    seenIdsRef.current = unreadIds;
  }, [notifications, personId]);
}
