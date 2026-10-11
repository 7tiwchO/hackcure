import Constants from 'expo-constants';
import { Platform } from 'react-native';

// In development, auto-detect host PC IP for physical devices via Expo hostUri
const getDevApiUrl = () => {
  const hostUri = Constants.expoConfig?.hostUri;
  if (hostUri) {
    const ip = hostUri.split(':')[0];
    if (ip && ip !== 'localhost' && ip !== '127.0.0.1') {
      return `http://${ip}:8000`;
    }
  }

  if (Platform.OS === 'android') {
    return 'http://10.0.2.2:8000';
  }
  return 'http://localhost:8000';
};

const configuredApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim().replace(/\/$/, '');
const configuredUrlIsLoopback = !!configuredApiUrl && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(configuredApiUrl);

// A loopback URL is correct for web and the iOS simulator, but on a physical
// phone it points back to the phone. Resolve it to the Expo host on native.
export const API_BASE_URL = configuredApiUrl && !(Platform.OS !== 'web' && configuredUrlIsLoopback)
  ? configuredApiUrl
  : getDevApiUrl();
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'hackcure_access_token',
  REFRESH_TOKEN: 'hackcure_refresh_token',
  USER_DATA: 'hackcure_user_data',
  SETTINGS: 'hackcure_settings',
  OFFLINE_QUEUE: 'hackcure_offline_queue',
  LANGUAGE: 'hackcure_language',
  THEME: 'hackcure_theme',
};

export const DEFAULT_PAGE_SIZE = 20;

export const DOSE_STATUS_CONFIG = {
  SCHEDULED: {
    color: '#3B82F6',
    bgColor: '#EFF6FF',
    labelKey: 'medications.scheduled',
    icon: 'clock',
  },
  DUE: {
    color: '#F59E0B',
    bgColor: '#FFFBEB',
    labelKey: 'medications.due',
    icon: 'alert-circle',
  },
  REMINDING: {
    color: '#D97706',
    bgColor: '#FEF3C7',
    labelKey: 'medications.reminding',
    icon: 'bell',
  },
  TAKEN_ON_TIME: {
    color: '#10B981',
    bgColor: '#ECFDF5',
    labelKey: 'medications.taken',
    icon: 'check-circle',
  },
  TAKEN_LATE: {
    color: '#EAB308',
    bgColor: '#FEFCE8',
    labelKey: 'medications.takenLate',
    icon: 'clock-alert',
  },
  MISSED: {
    color: '#EF4444',
    bgColor: '#FEF2F2',
    labelKey: 'medications.missed',
    icon: 'x-circle',
  },
  CANCELLED: {
    color: '#9CA3AF',
    bgColor: '#F3F4F6',
    labelKey: 'medications.cancelled',
    icon: 'slash',
  },
};
