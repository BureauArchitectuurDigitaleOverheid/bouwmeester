import { Check, ExternalLink } from 'lucide-react';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import type { ChatAction } from '@/api/chat';

interface ChatActionCardProps {
  action: ChatAction;
}

export function ChatActionCard({ action }: ChatActionCardProps) {
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();

  const canNavigate =
    action.entity_id &&
    (action.entity_type === 'node' || action.entity_type === 'task' || action.entity_type === 'tag');

  const handleClick = () => {
    if (!action.entity_id) return;
    if (action.entity_type === 'node' || action.entity_type === 'tag') {
      openNodeDetail(action.entity_id);
    } else if (action.entity_type === 'task') {
      openTaskDetail(action.entity_id);
    }
  };

  return (
    <div
      className={`flex items-start gap-2 p-2 rounded-md bg-green-50 border border-green-200 text-xs ${
        canNavigate ? 'cursor-pointer hover:bg-green-100 transition-colors' : ''
      }`}
      onClick={canNavigate ? handleClick : undefined}
      role={canNavigate ? 'button' : undefined}
      tabIndex={canNavigate ? 0 : undefined}
    >
      <Check className="w-3.5 h-3.5 text-green-600 mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-green-800">{action.description}</p>
        {action.result_summary && action.result_summary !== action.description && (
          <p className="text-green-600 truncate">{action.result_summary}</p>
        )}
      </div>
      {canNavigate && (
        <span className="flex items-center gap-0.5 text-green-600 shrink-0 mt-0.5">
          <span className="text-[10px]">Bekijken</span>
          <ExternalLink className="w-3 h-3" />
        </span>
      )}
    </div>
  );
}
