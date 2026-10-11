import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuthStore } from '../store/authStore';

/**
 * Small read-through cache for screens that must stay readable without network.
 * The last successful answer is kept on the device (per signed-in user) and is
 * served, flagged as `fromCache`, when the server cannot be reached.
 */
export interface CachedResult<T> {
  data: T;
  fromCache: boolean;
  cachedAt: string | null;
}

const cacheKey = (name: string) => `hackcure_cache_${name}_${useAuthStore.getState().user?.id ?? 'anonymous'}`;

const isUnreachable = (error: unknown) => {
  const status = (error as { response?: { status?: number } } | null)?.response?.status;
  return status === undefined || status >= 500;
};

export const writeOfflineCache = async <T,>(name: string, data: T): Promise<void> => {
  try {
    await AsyncStorage.setItem(cacheKey(name), JSON.stringify({ data, cachedAt: new Date().toISOString() }));
  } catch {
    // The cache is a convenience: never fail a screen because of it.
  }
};

export const clearOfflineCache = async (...names: string[]): Promise<void> => {
  try {
    await Promise.all(names.map((name) => AsyncStorage.removeItem(cacheKey(name))));
  } catch {
    // Ignored
  }
};

export const fetchWithOfflineCache = async <T,>(name: string, fetcher: () => Promise<T>): Promise<CachedResult<T>> => {
  try {
    const data = await fetcher();
    await writeOfflineCache(name, data);
    return { data, fromCache: false, cachedAt: null };
  } catch (error) {
    if (!isUnreachable(error)) throw error;
    try {
      const stored = await AsyncStorage.getItem(cacheKey(name));
      if (stored) {
        const parsed = JSON.parse(stored) as { data: T; cachedAt?: string };
        return { data: parsed.data, fromCache: true, cachedAt: parsed.cachedAt ?? null };
      }
    } catch {
      // Unreadable cache: fall through to the original error.
    }
    throw error;
  }
};
