import { useCallback, useRef } from 'react';
import type { Initiatief } from '@/types';
import { useNlddEvent, orUndef } from '@/components/nldd/events';
import { initiatiefIconColor } from './initiatiefColors';

/**
 * One initiative in the filter row, as a radio inside an
 * `nldd-toggle-button-group`.
 *
 * The group owns which one is on, so this only reports its own `change`
 * upward. The color sits in the leading dot rather than in the pill's fill:
 * the group paints the pill from its own selected/unselected tokens, which is
 * what keeps the state legible without relying on color.
 */
export function InitiatiefTogglePill({
  initiatief,
  selected,
  onSelect,
}: {
  initiatief: Initiatief;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(
    ref,
    'change',
    useCallback(() => onSelect(initiatief.id), [onSelect, initiatief.id]),
  );

  return (
    <nldd-toggle-button
      ref={ref}
      type="radio"
      size="sm"
      value={initiatief.id}
      text={initiatief.naam}
      selected={orUndef(selected)}
    >
      <nldd-icon
        slot="icon"
        name="circle-filled-small"
        color={initiatiefIconColor(initiatief.kleur)}
      />
    </nldd-toggle-button>
  );
}
