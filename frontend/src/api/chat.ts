import { apiPost } from './client';

export interface ChatContext {
  page: string;
  node_id?: string;
  node_title?: string;
  node_type?: string;
  node_description?: string;
  task_id?: string;
  task_title?: string;
}

export interface ChatAction {
  tool_name: string;
  description: string;
  result_summary: string;
  entity_id?: string;
  entity_type?: string;
}

export interface PendingAction {
  action_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  description: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  actions: ChatAction[];
  pending_actions: PendingAction[];
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  context?: ChatContext;
}

export interface ChatResponse {
  conversation_id: string;
  message: ChatMessage;
  available: boolean;
}

export interface ChatConfirmRequest {
  conversation_id: string;
  action_id: string;
  approved: boolean;
}

export interface ChatConfirmResponse {
  message: ChatMessage;
  success: boolean;
}

export function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  return apiPost<ChatResponse>('/api/chat', request);
}

export function confirmChatAction(request: ChatConfirmRequest): Promise<ChatConfirmResponse> {
  return apiPost<ChatConfirmResponse>('/api/chat/confirm', request);
}
