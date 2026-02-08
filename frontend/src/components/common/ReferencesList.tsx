import { Link as LinkIcon } from 'lucide-react';
import { Badge } from '@/components/common/Badge';
import { useReferences } from '@/hooks/useMentions';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';

interface ReferencesListProps {
  targetId: string;
}

export function ReferencesList({ targetId }: ReferencesListProps) {
  const { data: references } = useReferences(targetId);
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();

  if (!references || references.length === 0) return null;

  return (
    <div>
      <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
        <LinkIcon className="h-3.5 w-3.5 inline mr-1 -mt-0.5" />
        Verwijzingen ({references.length})
      </h4>
      <div className="space-y-1">
        {references.map((ref) => (
          <button
            key={`${ref.source_type}-${ref.source_id}`}
            onClick={() => {
              if (ref.source_type === 'node') openNodeDetail(ref.source_id);
              else if (ref.source_type === 'task') openTaskDetail(ref.source_id);
            }}
            className="flex items-center gap-2 w-full p-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
          >
            <Badge variant={ref.source_type === 'task' ? 'amber' : 'blue'}>
              {ref.source_type === 'node' ? 'Node' : ref.source_type === 'task' ? 'Taak' : ref.source_type}
            </Badge>
            <span className="text-sm text-text truncate">{ref.source_title}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
