import { useRef } from 'react';
import { Badge } from '@/components/common/Badge';
import { useNlddEvent } from '@/components/nldd/events';
import { useReferences } from '@/hooks/useMentions';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';

interface ReferencesListProps {
  targetId: string;
}

function ReferenceRow({
  label,
  title,
  variant,
  onOpen,
}: {
  label: string;
  title: string;
  variant: 'amber' | 'blue';
  onOpen: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onOpen);
  return (
    <nldd-list-item ref={ref} size="sm" button>
      <nldd-cell width="fit-content">
        <Badge variant={variant}>{label}</Badge>
      </nldd-cell>
      <nldd-text-cell text={title} />
    </nldd-list-item>
  );
}

export function ReferencesList({ targetId }: ReferencesListProps) {
  const { data: references } = useReferences(targetId);
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();

  if (!references || references.length === 0) return null;

  return (
    <nldd-container gap="8">
      <nldd-container layout="row" gap="4" vertical-alignment="center">
        <nldd-icon name="link" size="16" aria-hidden="true" />
        <nldd-text size="xs" weight="bold" color="secondary">
          Verwijzingen ({references.length})
        </nldd-text>
      </nldd-container>
      <nldd-list variant="simple" accessible-label="Verwijzingen">
        {references.map((ref) => (
          <ReferenceRow
            key={`${ref.source_type}-${ref.source_id}`}
            label={
              ref.source_type === 'node' ? 'Node' : ref.source_type === 'task' ? 'Taak' : ref.source_type
            }
            title={ref.source_title}
            variant={ref.source_type === 'task' ? 'amber' : 'blue'}
            onOpen={() => {
              if (ref.source_type === 'node') openNodeDetail(ref.source_id);
              else if (ref.source_type === 'task') openTaskDetail(ref.source_id);
            }}
          />
        ))}
      </nldd-list>
    </nldd-container>
  );
}
