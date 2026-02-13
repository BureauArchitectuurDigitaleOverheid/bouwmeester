import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const EMOJIS = ['👍', '👎', '❤️', '😊', '😂', '🎉', '👀', '🤔', '✅', '🔥', '💯', '👏'];

interface EmojiPickerProps {
  onSelect: (emoji: string) => void;
  onClose: () => void;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
}

export function EmojiPicker({ onSelect, onClose, anchorRef }: EmojiPickerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect();
      setPos({
        top: rect.top - 4,
        left: rect.left,
      });
    }
  }, [anchorRef]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        ref.current && !ref.current.contains(e.target as Node) &&
        anchorRef.current && !anchorRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose, anchorRef]);

  if (!pos) return null;

  return createPortal(
    <div
      ref={ref}
      className="fixed bg-surface border border-border rounded-lg shadow-lg p-2 grid grid-cols-6 gap-1 z-[60] w-[220px]"
      style={{ top: pos.top, left: pos.left, transform: 'translateY(-100%)' }}
    >
      {EMOJIS.map((emoji) => (
        <button
          key={emoji}
          onClick={() => {
            onSelect(emoji);
            onClose();
          }}
          className="w-8 h-8 flex items-center justify-center text-lg rounded hover:bg-gray-100 transition-colors"
        >
          {emoji}
        </button>
      ))}
    </div>,
    document.body,
  );
}
