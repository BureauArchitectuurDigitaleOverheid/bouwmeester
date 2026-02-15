import { X } from 'lucide-react';

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
        <span
          key={tag.name}
          className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-700 px-2.5 py-0.5 text-xs font-medium"
        >
          {tag.name}
          <button
            type="button"
            onClick={() => onRemove(tag.name)}
            className="hover:text-red-500 transition-colors ml-0.5"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
