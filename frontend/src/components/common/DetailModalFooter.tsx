import type { ReactNode } from 'react';
import { Button } from './Button';

interface DetailModalFooterProps {
  actions: ReactNode;
  onClose: () => void;
}

export function DetailModalFooter({ actions, onClose }: DetailModalFooterProps) {
  return (
    <div className="flex items-center justify-between w-full">
      <div className="flex items-center gap-2">{actions}</div>
      <Button variant="secondary" onClick={onClose}>
        Sluiten
      </Button>
    </div>
  );
}
