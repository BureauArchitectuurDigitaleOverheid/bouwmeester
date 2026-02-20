import { apiGet, apiPost, BASE_URL, getCsrfToken } from './client';

export interface ChatMention {
  id: string;
  label: string;
  type: string;
}

export interface ChatAttachment {
  id: string;
  bestandsnaam: string;
  content_type: string;
  bestandsgrootte: number;
}

export interface ChatContext {
  page: string;
  node_id?: string;
  node_title?: string;
  node_type?: string;
  node_description?: string;
  task_id?: string;
  task_title?: string;
  mentions?: ChatMention[];
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
  attachments?: ChatAttachment[];
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  context?: ChatContext;
  attachment_ids?: string[];
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

export interface ChatHistoryResponse {
  conversation_id: string;
  messages: ChatMessage[];
}

export function getChatHistory(id: string): Promise<ChatHistoryResponse> {
  return apiGet<ChatHistoryResponse>(`/api/chat/${id}`);
}

export function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  return apiPost<ChatResponse>('/api/chat', request);
}

export function confirmChatAction(request: ChatConfirmRequest): Promise<ChatConfirmResponse> {
  return apiPost<ChatConfirmResponse>('/api/chat/confirm', request);
}

export async function uploadChatAttachment(file: File): Promise<ChatAttachment> {
  const formData = new FormData();
  formData.append('file', file);

  const url = `${BASE_URL}/api/chat/upload`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    const text = await response.text();
    let detail = 'Upload mislukt';
    try {
      const body = JSON.parse(text);
      detail = body.detail || detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}

export function chatAttachmentPreviewUrl(attachmentId: string): string {
  return `${BASE_URL}/api/chat/attachments/${attachmentId}/preview`;
}

export function isImageContentType(contentType: string): boolean {
  return contentType.startsWith('image/');
}
