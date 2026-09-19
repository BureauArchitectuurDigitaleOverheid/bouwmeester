import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { Icon } from '@/components/nldd/Icon';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { formatDateTimeShort } from '@/utils/dates';
import { NOTIFICATION_TYPE_LABELS, INBOX_TYPE_COLORS } from '@/types';
import type { InboxItem as InboxItemType } from '@/types';

interface InboxItemProps {
  item: InboxItemType;
  onOpenThread?: (id: string) => void;
  onMarkRead?: (id: string) => void;
}

const typeIcons: Record<string, React.ReactNode> = {
  task: <Icon name="check-list" size="md" />,
  node: <Icon name="file-text" size="md" />,
  notification: <Icon name="bell" size="md" />,
  message: <Icon name="message-rectangle-text" size="md" />,
};


export function InboxItemCard({ item, onOpenThread, onMarkRead }: InboxItemProps) {
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();
  const { openLeadDetail } = useLeadDetail();

  const handleClick = () => {
    if (!item.read && onMarkRead) {
      onMarkRead(item.id);
    }
    if (item.type === 'message' && onOpenThread) {
      onOpenThread(item.id);
    } else if (item.task_id) {
      openTaskDetail(item.task_id);
    } else if (item.node_id) {
      openNodeDetail(item.node_id);
    } else if (item.lead_id) {
      openLeadDetail(item.lead_id);
    }
  };

  const isClickable = item.type === 'message' || !!item.task_id || !!item.node_id || !!item.lead_id;

  return (
    <Card hoverable={isClickable} onClick={handleClick}>
      <nldd-container layout="row" gap="12" vertical-alignment="top">
        {/* A 32px square icon badge with a read/unread background: nldd-container
            has no fixed-height attribute (only width/min-width/max-width) and no
            border-radius, so the box itself stays a plain styled div. The
            background/color are still tokens, not hex values. */}
        <div
          className="flex items-center justify-center h-8 w-8 rounded-lg shrink-0"
          style={
            item.read
              ? { background: 'var(--primitives-color-neutral-50)', color: 'var(--primitives-color-neutral-400)' }
              : { background: 'var(--primitives-color-accent-25)', color: 'var(--primitives-color-accent-700)' }
          }
        >
          {typeIcons[item.type] || <Icon name="bell" size="md" />}
        </div>

        <nldd-container layout="stack" gap="0" min-width="0" width="full">
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            {!item.read && (
              // A plain unread dot: nldd-badge is the design system's dot/count
              // overlay, but it anchors to a corner of ITS sibling (see
              // PersonAvatar's online dot) rather than sitting inline in a row,
              // which is what this needs.
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ background: 'var(--primitives-color-warning-500)' }}
              />
            )}
            {/* nldd-text has no truncate/ellipsis attribute, so the wrapper
                providing it stays plain CSS. */}
            <div className="truncate">
              <nldd-text size="sm" weight={item.read ? 'regular' : 'medium'} {...(item.read ? { color: 'secondary' } : {})}>
                {item.title}
              </nldd-text>
            </div>
          </nldd-container>

          {item.description && (
            // line-clamp-2 has no design-system equivalent either.
            <div className="text-xs line-clamp-2 mb-2">
              <RichTextDisplay content={item.description} fallback="" />
            </div>
          )}

          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <Badge variant={INBOX_TYPE_COLORS[item.type] ?? 'gray'}>
              {(item.notification_type && NOTIFICATION_TYPE_LABELS[item.notification_type]) || item.type}
            </Badge>
            {item.reply_count != null && item.reply_count > 0 && (
              <nldd-container layout="row" gap="4" vertical-alignment="center" width="fit-content">
                <Icon name="message-rectangle-text" size="xs" />
                <nldd-text size="xs" color="accent">
                  {item.reply_count} {item.reply_count === 1 ? 'reactie' : 'reacties'}
                </nldd-text>
              </nldd-container>
            )}
            <nldd-text size="xs" color="secondary">
              {formatDateTimeShort(item.created_at)}
            </nldd-text>
          </nldd-container>
        </nldd-container>
      </nldd-container>
    </Card>
  );
}
