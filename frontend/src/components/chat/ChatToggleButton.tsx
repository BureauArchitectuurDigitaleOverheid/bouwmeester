import { MessageSquare } from 'lucide-react';
import { useUIStore } from '@/store/ui';

export function ChatToggleButton() {
  const { chatOpen, toggleChat } = useUIStore();

  if (chatOpen) return null;

  return (
    <button
      onClick={toggleChat}
      className="fixed bottom-6 right-6 z-40 p-3 rounded-full bg-primary-600 text-white shadow-lg hover:bg-primary-700 hover:shadow-xl transition-all duration-200"
      title="AI Assistent"
    >
      <MessageSquare className="w-5 h-5" />
    </button>
  );
}
