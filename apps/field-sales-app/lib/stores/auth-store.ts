/**
 * Field Sales Auth Store — Zustand
 *
 * Manages field sales agent authentication state.
 * Uses expo-secure-store for native builds and localStorage for web/PWA.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface SalesAgentProfile {
  id: string;
  name: string;
  email: string;
  phone?: string;
  role: string;
  zone?: string;
}

interface AuthState {
  agent: SalesAgentProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  accessToken: string | null;
  refreshToken: string | null;

  setAuth: (agent: SalesAgentProfile, token: string) => void;
  setTokens: (access: string | null, refresh: string | null) => void;
  logout: () => void;
  clearError: () => void;
}

// Platform-aware storage adapter
// On native (Expo), uses SecureStore. On web/PWA, uses localStorage.
const getStorageAdapter = () => {
  try {
    const hasWindow = typeof window !== 'undefined';
    if (!hasWindow) {
      const SecureStore = require('expo-secure-store');
      return {
        getItem: async (name: string) => {
          const value = await SecureStore.getItemAsync(name);
          return value ?? null;
        },
        setItem: async (name: string, value: string) => {
          await SecureStore.setItemAsync(name, value);
        },
        removeItem: async (name: string) => {
          await SecureStore.deleteItemAsync(name);
        },
      };
    }
  } catch {
    // expo-secure-store not available, fall through to web storage
  }
  return undefined; // Let Zustand use its default localStorage storage
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      agent: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      accessToken: null,
      refreshToken: null,

      setAuth: (agent, token) =>
        set({ agent, isAuthenticated: true, accessToken: token, error: null }),

      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh }),

      logout: () =>
        set({
          agent: null,
          isAuthenticated: false,
          accessToken: null,
          refreshToken: null,
          error: null,
        }),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'field-sales-auth',
      storage: getStorageAdapter(),
      partialize: (state) => ({
        agent: state.agent,
        isAuthenticated: state.isAuthenticated,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);
