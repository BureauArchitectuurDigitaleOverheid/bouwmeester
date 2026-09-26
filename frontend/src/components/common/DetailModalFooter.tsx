import type { ReactNode } from 'react';
import { NlddButton } from '@/components/nldd/NlddButton';

interface DetailModalFooterProps {
  actions: ReactNode;
  onClose: () => void;
}

/**
 * The footer of a detail modal: its own actions on the left, close on the right.
 *
 * The distance between them is deliberate. The design guidelines put it this
 * way: do not place a destructive action next to the confirming one. Several of
 * these footers carry a delete, and close sits at the far end.
 */
export function DetailModalFooter({ actions, onClose }: DetailModalFooterProps) {
  return (
    <nldd-container layout="row" gap="8" vertical-alignment="center" width="full">
      {/* The left half takes the leftover space, which is what pushes close to
          the far end. Without row-fill it claims the container default of
          100% instead, and then close gets less room than its own label. */}
      <nldd-container
        layout="row"
        width="fit-content"
        className="row-fill"
        gap="8"
        vertical-alignment="center"
      >
        {actions}
      </nldd-container>
      <NlddButton variant="secondary" onClick={onClose} text="Sluiten" />
    </nldd-container>
  );
}
