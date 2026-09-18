import { useRef } from 'react';
import { useNlddEvent } from '@/components/nldd/events';

interface PendingTag {
  name: string;
  isNew: boolean;
}

interface PendingTagsListProps {
  tags: PendingTag[];
  onRemove: (name: string) => void;
}

export function PendingTagsList({ tags, onRemove }: PendingTagsListProps) {
  if (tags.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <PendingTagToken key={tag.name} name={tag.name} onRemove={() => onRemove(tag.name)} />
      ))}
    </div>
  );
}

/** A single pending-tag chip: `nldd-token` with its `dismiss` event bridged to React. */
function PendingTagToken({ name, onRemove }: { name: string; onRemove: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'dismiss', onRemove);
  return (
    <nldd-token ref={ref} text={name} control="dismiss" dismiss-text={`Verwijder tag ${name}`} />
  );
}
