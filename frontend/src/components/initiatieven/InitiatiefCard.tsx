import { Card } from '@/components/common/Card';
import type { Initiatief } from '@/types';

interface InitiatiefCardProps {
  initiatief: Initiatief;
  onClick: (initiatief: Initiatief) => void;
}

export function InitiatiefCard({ initiatief, onClick }: InitiatiefCardProps) {
  return (
    <Card hoverable onClick={() => onClick(initiatief)} padding={false}>
      <div className="flex flex-col">
        {/* Color swatch at the top */}
        <div
          className="h-2 w-full rounded-t-xl"
          style={{ backgroundColor: initiatief.kleur || '#94a3b8' }}
        />
        <div className="px-4 py-3 sm:px-5 sm:py-4 space-y-2">
          <h3 className="text-sm font-semibold text-text truncate">
            {initiatief.naam}
          </h3>
          {initiatief.beschrijving && (
            <p className="text-xs text-text-secondary line-clamp-2">
              {initiatief.beschrijving}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
