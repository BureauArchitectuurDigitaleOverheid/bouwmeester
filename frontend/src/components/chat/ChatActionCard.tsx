import { Check } from 'lucide-react';
import type { ChatAction } from '@/api/chat';

interface ChatActionCardProps {
  action: ChatAction;
}

export function ChatActionCard({ action }: ChatActionCardProps) {
  return (
    <div className="flex items-start gap-2 p-2 rounded-md bg-green-50 border border-green-200 text-xs">
      <Check className="w-3.5 h-3.5 text-green-600 mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium text-green-800">{action.description}</p>
        {action.result_summary && (
          <p className="text-green-600 truncate">{action.result_summary}</p>
        )}
      </div>
    </div>
  );
}
