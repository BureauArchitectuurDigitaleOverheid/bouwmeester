import type { ReactNode } from 'react';
import { Button } from './Button';

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
      <nldd-container layout="row" gap="8" vertical-alignment="center">
        {actions}
      </nldd-container>
      <nldd-container width="fit-content" horizontal-alignment="right">
        <Button variant="secondary" onClick={onClose}>
          Sluiten
        </Button>
      </nldd-container>
    </nldd-container>
  );
}
