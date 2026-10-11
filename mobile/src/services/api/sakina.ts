import { apiClient } from './client';

export interface SakinaMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface SakinaEmergencyNumber {
  label: string;
  number: string;
}

export interface SakinaContextUsed {
  grounded?: boolean;
  label?: string | null;
  sources?: string[] | null;
}

export interface SakinaReply {
  reply: string;
  crisis: boolean;
  fallback: boolean;
  emergency_numbers: SakinaEmergencyNumber[];
  /** Clinical context the reply was grounded on (optional, newer backends only). */
  context_used?: SakinaContextUsed | null;
  /** "offline_support": prepared supportive replies, no AI model was called. */
  mode?: 'llm' | 'offline_support' | null;
}

export const sakinaApi = {
  send: async (history: SakinaMessage[]) =>
    (await apiClient.post<SakinaReply>('/api/chat', { history }, { timeout: 70000 })).data,
};
