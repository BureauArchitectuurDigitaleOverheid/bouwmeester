import { useRef, type ReactNode } from 'react';
import { Badge } from './Badge';
import { useNlddEvent } from '@/components/nldd/events';
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

function ItemRow({ item }: { item: RelatedItem }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', item.onClick);

  // The arrow that used to fade in on hover is gone. It pointed at the row
  // itself, which the row already announces by being a button, and a hint that
  // only exists on hover never reaches a keyboard or a touch screen.
  return (
    <nldd-list-item ref={ref} size="sm" button>
      {item.icon && <nldd-cell width="fit-content">{item.icon}</nldd-cell>}
      {item.badge && (
        <nldd-cell width="fit-content">
          <Badge variant={item.badge.variant} dot={item.badge.dot}>
            {item.badge.text}
          </Badge>
        </nldd-cell>
      )}
      <nldd-text-cell text={item.label} />
      {item.secondaryText && (
        <nldd-text-cell
          text={item.secondaryText}
          color="secondary"
          width="fit-content"
          horizontal-alignment="right"
        />
      )}
    </nldd-list-item>
  );
}

export function RelatedItemsList({
  items,
  maxVisible = 5,
  onShowAll,
  showAllLabel,
  emptyLabel = 'Geen items',
}: RelatedItemsListProps) {
  if (items.length === 0) {
    return (
      <nldd-text size="sm" color="secondary">
        {emptyLabel}
      </nldd-text>
    );
  }

  const visible = items.slice(0, maxVisible);
  const hasMore = items.length > maxVisible;

  return (
    <nldd-container gap="4">
      <nldd-list variant="simple" accessible-label="Gerelateerde items">
        {visible.map((item) => (
          <ItemRow key={item.id} item={item} />
        ))}
      </nldd-list>
      {hasMore &&
        (onShowAll ? (
          <NlddTextButton
            text={showAllLabel ?? `Bekijk alle ${items.length} items`}
            onClick={onShowAll}
          />
        ) : (
          <nldd-text size="xs" color="secondary">
            +{items.length - maxVisible} meer
          </nldd-text>
        ))}
    </nldd-container>
  );
}

/** The "show all" link: an action, so a button, styled as a link. */
function NlddTextButton({ text, onClick }: { text: string; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return <nldd-button ref={ref} text={text} variant="accent-transparent" size="sm" />;
}
