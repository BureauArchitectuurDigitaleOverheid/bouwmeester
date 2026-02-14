import { FileText, CheckSquare, Bell, MessageSquare, MessageCircle } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { formatDateTimeShort } from '@/utils/dates';
import { NOTIFICATION_TYPE_LABELS, INBOX_TYPE_COLORS } from '@/types';
import type { InboxItem as InboxItemType } from '@/types';

interface InboxItemProps {
  item: InboxItemType;
  onOpenThread?: (id: string) => void;
  onMarkRead?: (id: string) => void;
}

const typeIcons: Record<string, React.ReactNode> = {
  task: <CheckSquare className="h-4 w-4" />,
  node: <FileText className="h-4 w-4" />,
  notification: <Bell className="h-4 w-4" />,
  message: <MessageSquare className="h-4 w-4" />,
};


export function InboxItemCard({ item, onOpenThread, onMarkRead }: InboxItemProps) {
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();

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
    }
  };

  const isClickable = item.type === 'message' || !!item.task_id || !!item.node_id;

  return (
    <Card hoverable={isClickable} onClick={handleClick}>
      <div className="flex items-start gap-3">
        <div
          className={`flex items-center justify-center h-8 w-8 rounded-lg shrink-0 ${
            item.read ? 'bg-gray-100 text-gray-400' : 'bg-primary-50 text-primary-700'
          }`}
        >
          {typeIcons[item.type] || <Bell className="h-4 w-4" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            {!item.read && (
              <span className="h-2 w-2 rounded-full bg-accent-500 shrink-0" />
            )}
            <h4
              className={`text-sm truncate ${
                item.read ? 'text-text-secondary font-normal' : 'text-text font-medium'
              }`}
            >
              {item.title}
            </h4>
          </div>

          {item.description && (
            <div className="text-xs line-clamp-2 mb-2">
              <RichTextDisplay content={item.description} fallback="" />
            </div>
          )}

          <div className="flex items-center gap-2">
            <Badge variant={INBOX_TYPE_COLORS[item.type] ?? 'gray'}>
              {(item.notification_type && NOTIFICATION_TYPE_LABELS[item.notification_type]) || item.type}
            </Badge>
            {item.reply_count != null && item.reply_count > 0 && (
              <span className="flex items-center gap-1 text-xs text-primary-600">
                <MessageCircle className="h-3 w-3" />
                {item.reply_count} {item.reply_count === 1 ? 'reactie' : 'reacties'}
              </span>
            )}
            <span className="text-xs text-text-secondary">
              {formatDateTimeShort(item.created_at)}
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}
