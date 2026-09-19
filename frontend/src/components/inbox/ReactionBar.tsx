import { useCallback, useRef, useState } from 'react';
import { useNlddEvent } from '@/components/nldd/events';
import { Icon } from '@/components/nldd/Icon';
import { EmojiPicker } from './EmojiPicker';
import type { ReactionSummary } from '@/types';

interface ReactionChipProps {
  reaction: ReactionSummary;
  onReact: (emoji: string) => void;
}

function ReactionChip({ reaction, onReact }: ReactionChipProps) {
  const ref = useRef<HTMLElement>(null);
  const handleClick = useCallback(() => onReact(reaction.emoji), [onReact, reaction.emoji]);
  useNlddEvent(ref, 'click', handleClick);

  return (
    <nldd-button
      ref={ref}
      size="xs"
      variant={reaction.reacted_by_me ? 'accent-transparent' : 'neutral-transparent'}
      text={`${reaction.emoji} ${reaction.count}`}
      accessible-label={`${reaction.emoji} ${reaction.count}, ${reaction.sender_names.join(', ')}`}
    />
  );
}

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
    <nldd-container layout="wrap" gap="4" vertical-alignment="center">
      {reactions.map((r) => (
        <ReactionChip key={r.emoji} reaction={r} onReact={onReact} />
      ))}
      {/* EmojiPicker anchors itself via getBoundingClientRect on a real DOM
          button ref, so this trigger stays a native <button> (matching the
          special case documented in EmojiPicker.tsx) rather than becoming an
          nldd-icon-button, which would nest one control inside another. */}
      <button
        ref={btnRef}
        onClick={() => setPickerOpen(!pickerOpen)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '24px',
          height: '24px',
          borderRadius: '9999px',
        }}
        aria-label="Reactie toevoegen"
      >
        <Icon name="face-smiling-badge-plus" size="sm" color="secondary-content" />
      </button>
      {pickerOpen && (
        <EmojiPicker
          anchorRef={btnRef}
          onSelect={onReact}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </nldd-container>
  );
}
