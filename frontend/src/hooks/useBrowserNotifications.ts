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
  // Tracks every unread notification ID we've ever encountered (grow-only).
  // This prevents re-firing for notifications that were read and then reappear
  // as unread in a later poll (race condition / eventual consistency).
  const seenIdsRef = useRef<Set<string> | null>(null);
  const prevPersonIdRef = useRef<string | undefined>(personId);

  useEffect(() => {
    // Reset tracking when personId changes
    if (prevPersonIdRef.current !== personId) {
      seenIdsRef.current = null;
      prevPersonIdRef.current = personId;
    }

    if (!notifications || !personId) return;

    const unreadIds = notifications
      .filter((n) => !n.is_read)
      .map((n) => n.id);

    // First load: seed without firing
    if (seenIdsRef.current === null) {
      seenIdsRef.current = new Set(unreadIds);
      return;
    }

    // Find genuinely new unread IDs (not yet in our grow-only set)
    const newIds = unreadIds.filter((id) => !seenIdsRef.current!.has(id));

    // Add all current unread IDs to the seen set (grow-only, never shrink)
    for (const id of unreadIds) {
      seenIdsRef.current.add(id);
    }

    // Guard: user must have opted in, permission must be granted
    if (
      newIds.length === 0 ||
      !isBrowserNotificationsEnabled() ||
      !('Notification' in window) ||
      Notification.permission !== 'granted'
    ) {
      return;
    }

    // Fire browser notifications for genuinely new unread items
    for (const id of newIds) {
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
          tag: notification.id, // deduplicates at OS level
        });
        n.onclick = () => {
          window.focus();
          n.close();
        };
      }
    }
  }, [notifications, personId]);
}
