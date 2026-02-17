import type { ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import { Badge } from './Badge';
import type { BadgeVariant } from '@/types';

interface RelatedItem {
  id: string;
  label: string;
  badge?: { text: string; variant: BadgeVariant; dot?: boolean };
  secondaryText?: string;
  icon?: ReactNode;
  onClick: () => void;
}

interface RelatedItemsListProps {
  items: RelatedItem[];
  maxVisible?: number;
  onShowAll?: () => void;
  showAllLabel?: string;
  emptyLabel?: string;
}

export function RelatedItemsList({
  items,
  maxVisible = 5,
  onShowAll,
  showAllLabel,
  emptyLabel = 'Geen items',
}: RelatedItemsListProps) {
  if (items.length === 0) {
    return <p className="text-sm text-text-secondary">{emptyLabel}</p>;
  }

  const visible = items.slice(0, maxVisible);
  const hasMore = items.length > maxVisible;

  return (
    <div className="space-y-0.5">
      {visible.map((item) => (
        <button
          key={item.id}
          onClick={item.onClick}
          className="flex items-center gap-2 w-full p-1.5 rounded-lg hover:bg-gray-50 transition-colors text-left group"
        >
          {item.icon}
          {item.badge && (
            <Badge variant={item.badge.variant} dot={item.badge.dot}>
              {item.badge.text}
            </Badge>
          )}
          <span className="text-sm text-text truncate flex-1 group-hover:text-primary-700 transition-colors">
            {item.label}
          </span>
          {item.secondaryText && (
            <span className="text-xs text-text-secondary shrink-0">
              {item.secondaryText}
            </span>
          )}
          <ArrowRight className="h-3.5 w-3.5 text-gray-300 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      ))}
      {hasMore && onShowAll && (
        <button
          onClick={onShowAll}
          className="text-xs text-primary-700 hover:text-primary-900 transition-colors pl-1.5 pt-1"
        >
          {showAllLabel ?? `Bekijk alle ${items.length} items`}
        </button>
      )}
    </div>
  );
}
