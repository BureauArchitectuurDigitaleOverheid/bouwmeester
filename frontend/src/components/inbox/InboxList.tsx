import { InboxItemCard } from './InboxItem';
import { EmptyState } from '@/components/common/EmptyState';
import type { InboxItem } from '@/types';

interface InboxListProps {
  items: InboxItem[];
  onOpenThread?: (id: string) => void;
  onMarkRead?: (id: string) => void;
}

const GROUP_LABELS: Record<string, string> = {
  task: 'Taken',
  node: 'Corpus',
  notification: 'Meldingen',
  message: 'Berichten',
};

export function InboxList({ items, onOpenThread, onMarkRead }: InboxListProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon="inbox"
        title="Inbox is leeg"
        description="Er zijn geen nieuwe berichten of meldingen. Zodra er activiteit is, verschijnt deze hier."
      />
    );
  }

  // Group by type
  const grouped = items.reduce(
    (groups, item) => {
      if (!groups[item.type]) groups[item.type] = [];
      groups[item.type].push(item);
      return groups;
    },
    {} as Record<string, InboxItem[]>,
  );

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([type, groupItems]) => (
        <div key={type}>
          <div className="mb-2 uppercase tracking-wider">
            <nldd-text size="xs" weight="bold" color="secondary">
              {GROUP_LABELS[type] ?? type} ({groupItems.length})
            </nldd-text>
          </div>
          <div className="space-y-2">
            {groupItems.map((item) => (
              <InboxItemCard key={item.id} item={item} onOpenThread={onOpenThread} onMarkRead={onMarkRead} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
