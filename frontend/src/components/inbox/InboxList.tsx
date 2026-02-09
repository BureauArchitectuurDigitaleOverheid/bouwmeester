import { InboxItemCard } from './InboxItem';
import { EmptyState } from '@/components/common/EmptyState';
import { Inbox } from 'lucide-react';
import type { InboxItem } from '@/types';

interface InboxListProps {
  items: InboxItem[];
  onOpenThread?: (id: string) => void;
}

export function InboxList({ items, onOpenThread }: InboxListProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Inbox className="h-16 w-16" />}
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
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
            {type} ({groupItems.length})
          </h3>
          <div className="space-y-2">
            {groupItems.map((item) => (
              <InboxItemCard key={item.id} item={item} onOpenThread={onOpenThread} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
