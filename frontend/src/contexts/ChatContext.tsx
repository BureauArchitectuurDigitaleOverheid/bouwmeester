import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  sendChatMessage,
  confirmChatAction,
  type ChatMessage,
  type ChatMention,
  type ChatContext as ChatContextType,
} from '@/api/chat';
import { queryKeys } from '@/hooks/queryKeys';

interface ChatContextValue {
  conversationId: string | null;
  messages: ChatMessage[];
  isLoading: boolean;
  available: boolean;
  sendMessage: (text: string, mentions?: ChatMention[]) => Promise<void>;
  confirmAction: (actionId: string, approved: boolean) => Promise<void>;
  clearConversation: () => void;
}

const ChatCtx = createContext<ChatContextValue | null>(null);

const STORAGE_KEY = 'bm_chat_conversation_id';

function getStoredConversationId(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function setStoredConversationId(id: string | null): void {
  try {
    if (id) {
      sessionStorage.setItem(STORAGE_KEY, id);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // sessionStorage unavailable
  }
}

/** Map entity_type from a confirmed action to React Query keys to invalidate. */
function getInvalidationKeys(entityType: string | undefined) {
  switch (entityType) {
    case 'node':
      return [queryKeys.nodes.all, queryKeys.graph.all];
    case 'task':
      return [queryKeys.tasks.all];
    case 'edge':
      return [queryKeys.edges.all, queryKeys.nodes.all, queryKeys.graph.all];
    case 'tag':
      return [queryKeys.tags.all, queryKeys.nodes.all];
    case 'opdracht':
      return [queryKeys.opdrachten.all];
    default:
      return [];
  }
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(getStoredConversationId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [available, setAvailable] = useState(true);

  const getContext = useCallback((): ChatContextType => {
    const path = location.pathname;
    const ctx: ChatContextType = { page: path };

    // Extract node context from /nodes/:id paths
    const nodeMatch = path.match(/^\/nodes\/([a-f0-9-]+)/i);
    if (nodeMatch) {
      ctx.node_id = nodeMatch[1];
    }

    return ctx;
  }, [location.pathname]);

  const sendMessage = useCallback(async (text: string, mentions?: ChatMention[]) => {
    const userMsg: ChatMessage = {
      role: 'user',
      content: text,
      actions: [],
      pending_actions: [],
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const ctx = getContext();
      if (mentions?.length) {
        ctx.mentions = mentions;
      }
      const response = await sendChatMessage({
        message: text,
        conversation_id: conversationId ?? undefined,
        context: ctx,
      });

      setConversationId(response.conversation_id);
      setStoredConversationId(response.conversation_id);
      setAvailable(response.available);
      setMessages((prev) => [...prev, response.message]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Er is een fout opgetreden. Probeer het opnieuw.',
          actions: [],
          pending_actions: [],
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId, getContext]);

  const confirmAction = useCallback(async (actionId: string, approved: boolean) => {
    if (!conversationId) return;
    setIsLoading(true);

    try {
      const response = await confirmChatAction({
        conversation_id: conversationId,
        action_id: actionId,
        approved,
      });

      // Remove pending action from last message, add result message
      setMessages((prev) => {
        const updated = prev.map((msg) => ({
          ...msg,
          pending_actions: msg.pending_actions.filter((pa) => pa.action_id !== actionId),
        }));
        return [...updated, response.message];
      });

      // Invalidate relevant queries
      if (approved && response.message.actions) {
        for (const action of response.message.actions) {
          const keys = getInvalidationKeys(action.entity_type);
          for (const key of keys) {
            await queryClient.invalidateQueries({ queryKey: key });
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Fout bij het verwerken van de bevestiging.',
          actions: [],
          pending_actions: [],
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId, queryClient]);

  const clearConversation = useCallback(() => {
    setConversationId(null);
    setMessages([]);
    setStoredConversationId(null);
    setAvailable(true);
  }, []);

  const value = useMemo(
    () => ({ conversationId, messages, isLoading, available, sendMessage, confirmAction, clearConversation }),
    [conversationId, messages, isLoading, available, sendMessage, confirmAction, clearConversation],
  );

  return <ChatCtx.Provider value={value}>{children}</ChatCtx.Provider>;
}

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatCtx);
  if (!ctx) throw new Error('useChat must be used within ChatProvider');
  return ctx;
}
