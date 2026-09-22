import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotifications, useUnreadCount, useMarkNotificationRead, useMarkAllNotificationsRead } from '@/hooks/useNotifications';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { useNlddEvent, orUndef } from '@/components/nldd/events';
import { timeAgo } from '@/utils/dates';
import type { Notification } from '@/types';
import { richTextToPlain } from '@/utils/richtext';
import { MessageThread } from '@/components/inbox/MessageThread';
import { NOTIFICATION_TYPE_COLORS, NOTIFICATION_TYPE_LABELS, titleCase } from '@/types';
import {
  useBrowserNotifications,
  isBrowserNotificationsEnabled,
  setBrowserNotificationsEnabled,
  isNotificationSoundEnabled,
  setNotificationSoundEnabled,
  requestNotificationPermission,
} from '@/hooks/useBrowserNotifications';
import { useToast } from '@/contexts/ToastContext';

type TagColor = NonNullable<React.ComponentProps<'nldd-tag'>['color']>;

function NotificationItem({
  notification,
  onMarkRead,
  onClick,
}: {
  notification: Notification;
  onMarkRead: (id: string) => void;
  onClick?: () => void;
}) {
  const label =
    NOTIFICATION_TYPE_LABELS[notification.type] || titleCase(notification.type.replace(/_/g, ' '));
  const body = richTextToPlain(notification.last_message ?? notification.message ?? '');

  const rowRef = useRef<HTMLElement>(null);
  useNlddEvent(rowRef, 'click', onClick);

  // A row is built from cells, never from loose text: the cell sets the type
  // scale, the color and the alignment against the row height. Text dropped
  // straight into a button row inherits the browser's button styling instead.
  //
  // The tag and the timestamp sit ABOVE the title, in the same cell, not
  // beside it. A list item lays its cells out in one row, so as separate
  // cells they competed with the title for the popover's 360px and the two
  // printed over each other.
  return (
    <nldd-list-item
      ref={rowRef}
      size="md"
      button={orUndef(Boolean(onClick))}
      selected={orUndef(!notification.is_read)}
    >
      {/* `width="full"` because a cell does not claim the leftover space on
          its own: without it this one measured zero and the title came out
          one letter per line. */}
      <nldd-cell width="full">
        <nldd-container gap="4">
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <nldd-tag
              text={label}
              color={(NOTIFICATION_TYPE_COLORS[notification.type] ?? 'neutral') as TagColor}
              size="sm"
              className="row-badge"
            />
            <nldd-text size="xs" color="secondary">
              {timeAgo(notification.last_activity_at ?? notification.created_at)}
            </nldd-text>
          </nldd-container>
          <nldd-text-cell
            text={notification.title}
            {...(body ? { 'supporting-text': body } : {})}
          />
        </nldd-container>
      </nldd-cell>

      {!notification.is_read && (
        <nldd-cell width="fit-content">
          <NlddIconButton
            icon="check-mark"
            variant="neutral-transparent"
            size="sm"
            accessible-label="Markeer als gelezen"
            no-tab
            onClick={(e) => {
              e.stopPropagation();
              onMarkRead(notification.id);
            }}
          />
        </nldd-cell>
      )}
    </nldd-list-item>
  );
}

/** An nldd-icon-button that reports clicks through the element's own event. */
function NlddIconButton({
  onClick,
  ...props
}: React.ComponentProps<'nldd-icon-button'> & {
  onClick?: (event: MouseEvent) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', (e) => onClick?.(e as MouseEvent));
  return <nldd-icon-button ref={ref} {...props} />;
}

/** Same, for nldd-toggle-button. */
function NlddToggleButton({
  onClick,
  ...props
}: React.ComponentProps<'nldd-toggle-button'> & {
  onClick?: (event: MouseEvent) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', (e) => onClick?.(e as MouseEvent));
  // `shrink-0`: these sit in the popover header beside a heading that takes
  // the leftover space, and an icon button has nothing to give up.
  return <nldd-toggle-button ref={ref} className="shrink-0" {...props} />;
}

function BrowserNotificationToggle() {
  const [enabled, setEnabled] = useState(isBrowserNotificationsEnabled);
  const { showError } = useToast();

  if (!('Notification' in window)) return null;

  const handleToggle = async () => {
    if (enabled) {
      setBrowserNotificationsEnabled(false);
      setEnabled(false);
      return;
    }
    const permission = await requestNotificationPermission();
    if (permission === 'granted') {
      setBrowserNotificationsEnabled(true);
      setEnabled(true);
    } else if (permission === 'denied') {
      showError('Browsermeldingen zijn geblokkeerd. Sta meldingen toe in je browserinstellingen.');
    }
  };

  // A toggle button, not an icon button with two icons: there is no bell-slash
  // in the icon set, and the state belongs in aria-pressed anyway. The pressed
  // state is what says whether notifications are on, so it is announced rather
  // than left to whichever glyph is showing.
  return (
    <NlddToggleButton
      icon="bell"
      size="sm"
      selected={orUndef(enabled)}
      accessible-label={enabled ? 'Browsermeldingen uitschakelen' : 'Browsermeldingen inschakelen'}
      onClick={() => void handleToggle()}
    />
  );
}

function NotificationSoundToggle() {
  const [soundOn, setSoundOn] = useState(isNotificationSoundEnabled);
  const notificationsOn = isBrowserNotificationsEnabled();

  if (!notificationsOn) return null;

  // This one does have a real pair of glyphs, so the icon changes as well as
  // the pressed state.
  return (
    <NlddToggleButton
      icon={soundOn ? 'speaker-volume-high' : 'speaker-slash'}
      size="sm"
      selected={orUndef(soundOn)}
      accessible-label={soundOn ? 'Geluid uitschakelen' : 'Geluid inschakelen'}
      onClick={() => {
        const next = !soundOn;
        setNotificationSoundEnabled(next);
        setSoundOn(next);
      }}
    />
  );
}

export function NotificationBell() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const popoverRef = useRef<HTMLElement>(null);
  const navigate = useNavigate();
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();
  const { openLeadDetail } = useLeadDetail();
  const { currentPerson } = useCurrentPerson();

  useBrowserNotifications();

  const { data: countData } = useUnreadCount();
  const { data: notifications } = useNotifications(false);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const unreadCount = countData?.count ?? 0;

  if (!currentPerson) return null;

  // The component's own hide(), not the native hidePopover(): it no-ops when the
  // popover is already closed instead of throwing.
  const close = () => (popoverRef.current as { hide?: () => void } | null)?.hide?.();

  // Every branch marks read (where it applies), routes, and closes. The routing
  // is what differs, so only that is per-type.
  const handleOpen = (notification: Notification) => {
    const type = notification.type;
    if (type === 'direct_message' || type === 'agent_prompt') {
      setThreadId(notification.id);
      close();
      return;
    }

    if (type === 'access_request') navigate('/admin?tab=requests');
    else if (type === 'placement_request') navigate('/admin?tab=placements');
    else if (notification.related_task_id) openTaskDetail(notification.related_task_id);
    else if (notification.related_node_id) openNodeDetail(notification.related_node_id);
    else if (notification.related_lead_id) openLeadDetail(notification.related_lead_id);
    else return;

    if (!notification.is_read) markRead.mutate(notification.id);
    close();
  };

  return (
    <>
      {/* The popover sits in the button's `popup` slot, so the browser owns
          opening, toggling and light dismiss, and the button gets its
          aria-expanded and aria-haspopup wired up for free. The previous
          version did all of that by hand with a mousedown listener on
          document. On a narrow screen the popover becomes a bottom sheet by
          itself, which is what the fixed/absolute breakpoint dance replaced. */}
      <nldd-icon-button
        icon="bell"
        variant="neutral-transparent"
        accessible-label={
          unreadCount > 0 ? `Meldingen (${unreadCount} ongelezen)` : 'Meldingen'
        }
        popup-type="dialog"
      >
        {unreadCount > 0 && (
          <nldd-badge
            number={unreadCount}
            max={99}
            color="critical"
            size="sm"
            accessible-label={`${unreadCount} ongelezen meldingen`}
          />
        )}

        <nldd-popover
          slot="popup"
          ref={popoverRef}
          accessible-label="Meldingen"
          width="360px"
          placement="bottom-end"
          sm-full-height
        >
          <nldd-container gap="0">
            {/* The buttons sit in the row themselves, without a container of
                their own. Wrapped in one they measured zero and hung over the
                popover's right edge: `width="fit-content"` gives a container
                no floor, so the heading beside it took all 360px. Each button
                keeps its own width through `shrink-0`, and the heading gets
                what is left. */}
            <nldd-container layout="row" gap="4" vertical-alignment="center" padding="12">
              <nldd-container width="fit-content" className="row-fill">
                <nldd-title size={5}><h2>Meldingen</h2></nldd-title>
              </nldd-container>
              <BrowserNotificationToggle />
              <NotificationSoundToggle />
              {unreadCount > 0 && (
                <NlddIconButton
                  icon="checked"
                  variant="neutral-transparent"
                  size="sm"
                  accessible-label="Alles markeren als gelezen"
                  onClick={() => markAllRead.mutate()}
                  className="shrink-0"
                />
              )}
            </nldd-container>

            <nldd-divider />

            {notifications && notifications.length > 0 ? (
              <nldd-list variant="simple" accessible-label="Meldingen">
                {notifications.map((notification) => (
                  <NotificationItem
                    key={notification.id}
                    notification={notification}
                    onMarkRead={(id) => markRead.mutate(id)}
                    onClick={() => handleOpen(notification)}
                  />
                ))}
              </nldd-list>
            ) : (
              <nldd-container padding="24" horizontal-alignment="center">
                <nldd-text size="sm" color="secondary">
                  Geen meldingen
                </nldd-text>
              </nldd-container>
            )}
          </nldd-container>
        </nldd-popover>
      </nldd-icon-button>

      {threadId && (
        <MessageThread notificationId={threadId} onClose={() => setThreadId(null)} />
      )}
    </>
  );
}
