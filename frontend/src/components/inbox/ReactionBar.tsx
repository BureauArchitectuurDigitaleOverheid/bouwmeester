import { useRef, useState } from 'react';
import { SmilePlus } from 'lucide-react';
import { EmojiPicker } from './EmojiPicker';
import type { ReactionSummary } from '@/api/notifications';

interface ReactionBarProps {
  reactions: ReactionSummary[];
  onReact: (emoji: string) => void;
}

export function ReactionBar({ reactions, onReact }: ReactionBarProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

  if (reactions.length === 0 && !pickerOpen) {
    return null;
  }

  return (
    <div className="flex items-center gap-1 flex-wrap mt-1">
      {reactions.map((r) => (
        <button
          key={r.emoji}
          onClick={() => onReact(r.emoji)}
          title={r.sender_names.join(', ')}
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs border transition-colors ${
            r.reacted_by_me
              ? 'border-primary-300 bg-primary-50 text-primary-700'
              : 'border-border bg-gray-50 text-text-secondary hover:bg-gray-100'
          }`}
        >
          <span>{r.emoji}</span>
          <span>{r.count}</span>
        </button>
      ))}
      <button
        ref={btnRef}
        onClick={() => setPickerOpen(!pickerOpen)}
        className="inline-flex items-center justify-center w-6 h-6 rounded-full text-text-secondary hover:bg-gray-100 transition-colors"
      >
        <SmilePlus className="h-3.5 w-3.5" />
      </button>
      {pickerOpen && (
        <EmojiPicker
          anchorRef={btnRef}
          onSelect={onReact}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  );
}
