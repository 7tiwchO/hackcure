import { apiClient } from './client';
import { AgentRun, CareProgram } from '../../types';

export const programApi = {
  /** Returns null when the agent has not generated anything yet (HTTP 404). */
  getProgram: async (): Promise<CareProgram | null> => {
    try {
      const response = await apiClient.get<CareProgram>('/api/care-program');
      return response.data ?? null;
    } catch (error) {
      if ((error as { response?: { status?: number } } | null)?.response?.status === 404) return null;
      throw error;
    }
  },

  getAgentRuns: async (limit: number = 10): Promise<AgentRun[]> => {
    const response = await apiClient.get<AgentRun[]>('/api/agent/runs', { params: { limit } });
    return Array.isArray(response.data) ? response.data : [];
  },
};
