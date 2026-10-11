import { apiClient } from './client';
import { HospitalLinkRequest, HospitalLinkStatus } from '../../types';

export const hospitalLinkApi = {
  getStatus: async (): Promise<HospitalLinkStatus> => {
    const response = await apiClient.get<HospitalLinkStatus>('/api/hospital-link');
    return response.data;
  },

  link: async (payload: HospitalLinkRequest): Promise<HospitalLinkStatus> => {
    const response = await apiClient.post<HospitalLinkStatus>('/api/hospital-link', payload, { timeout: 30000 });
    return response.data;
  },

  sync: async (): Promise<HospitalLinkStatus> => {
    const response = await apiClient.post<HospitalLinkStatus>('/api/hospital-link/sync', undefined, { timeout: 30000 });
    return response.data;
  },

  unlink: async (): Promise<{ linked: false }> => {
    const response = await apiClient.delete<{ linked: false }>('/api/hospital-link');
    return response.data;
  },
};
