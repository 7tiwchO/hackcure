import { apiClient } from './client';
import { Subscription, SubscriptionPlan } from '../../types';

export const subscriptionApi = {
  get: async (): Promise<Subscription> => {
    const response = await apiClient.get<Subscription>('/api/subscription');
    return response.data;
  },

  /** Demonstration only: no payment is taken anywhere. */
  activate: async (plan: SubscriptionPlan): Promise<Subscription> => {
    const response = await apiClient.post<Subscription>('/api/subscription/activate', { plan });
    return response.data;
  },
};
