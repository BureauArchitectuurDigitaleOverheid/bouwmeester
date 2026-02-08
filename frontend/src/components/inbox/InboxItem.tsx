import { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, CheckSquare, Bell, MessageSquare } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import type { InboxItem as InboxItemType } from '@/types';

interface InboxItemProps {
  item: InboxItemType;
  highlighted?: boolean;
}

const typeIcons: Record<string, React.ReactNode> = {
  task: <CheckSquare className="h-4 w-4" />,
  node: <FileText className="h-4 w-4" />,
  notification: <Bell className="h-4 w-4" />,
  message: <MessageSquare className="h-4 w-4" />,
};

const typeColors: Record<string, string> = {
  task: 'blue',
  node: 'purple',
  notification: 'amber',
  message: 'green',
};

export function InboxItemCard({ item, highlighted }: InboxItemProps) {
  const navigate = useNavigate();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highlighted && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlighted]);

  const handleClick = () => {
    if (item.node_id) {
      navigate(`/nodes/${item.node_id}`);
    }
  };

  return (
    <div ref={ref}>
    <Card hoverable={!!item.node_id} onClick={handleClick} className={highlighted ? 'ring-2 ring-primary-400' : ''}>
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
            <p className="text-xs text-text-secondary line-clamp-2 mb-2">
              {item.description}
            </p>
          )}

          <div className="flex items-center gap-2">
            <Badge variant={typeColors[item.type] as 'blue'}>
              {item.type}
            </Badge>
            <span className="text-xs text-text-secondary">
              {new Date(item.created_at).toLocaleDateString('nl-NL', {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>
        </div>
      </div>
    </Card>
    </div>
  );
}
