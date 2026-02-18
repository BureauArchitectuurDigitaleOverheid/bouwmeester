import { Trash2, X } from 'lucide-react';
import { useChat } from '@/contexts/ChatContext';
import { useUIStore } from '@/store/ui';

export function ChatHeader() {
  const { clearConversation } = useChat();
  const setChatOpen = useUIStore((s) => s.setChatOpen);

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-white">
      <h2 className="text-sm font-semibold text-text">Assistent</h2>
      <div className="flex items-center gap-1">
        <button
          onClick={clearConversation}
          className="p-1.5 rounded-md text-text-secondary hover:text-text hover:bg-gray-100 transition-colors"
          title="Gesprek wissen"
        >
          <Trash2 className="w-4 h-4" />
        </button>
        <button
          onClick={() => setChatOpen(false)}
          className="p-1.5 rounded-md text-text-secondary hover:text-text hover:bg-gray-100 transition-colors"
          title="Sluiten"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
