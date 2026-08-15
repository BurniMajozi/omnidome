/**
 * Technician Auth Store — Zustand
 *
 * Manages technician authentication state.
 * Uses expo-secure-store for native builds and localStorage for web/PWA.
 */
import { create } from 'zustand';
import { persist, type PersistStorage, type StorageValue } from 'zustand/middleware';
import type { TechnicianProfile } from '../api/types';

interface AuthState {
  technician: TechnicianProfile | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  accessToken: string | null
  refreshToken: string | null

  setAuth: (tech: TechnicianProfile, token: string) => void
  setTokens: (access: string | null, refresh: string | null) => void
  logout: () => void
  clearError: () => void
}

// Platform-aware storage adapter.
// On native (Expo WebView shell), `window` is undefined, so we use
// expo-secure-store. On web/PWA, `window` exists and we fall through to
// Zustand's default localStorage. (The earlier comment was inverted — the
// `!hasWindow` branch below is the native path, not the web path.)
const getStorageAdapter = (): PersistStorage<AuthState> | undefined => {
  try {
    const hasWindow = typeof window !== 'undefined';
    if (!hasWindow) {
      const SecureStore = require('expo-secure-store');
      const adapter: PersistStorage<AuthState> = {
        getItem: async (name: string) => {
          const value = await SecureStore.getItemAsync(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: async (name: string, value: StorageValue<AuthState>) => {
          await SecureStore.setItemAsync(name, JSON.stringify(value));
        },
        removeItem: async (name: string) => {
          await SecureStore.deleteItemAsync(name);
        },
      };
      return adapter;
    }
  } catch {
    // expo-secure-store not available, fall through to web storage
  }
  return undefined; // Let Zustand use its default localStorage storage
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      technician: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      accessToken: null,
      refreshToken: null,

      setAuth: (tech, token) =>
        set({ technician: tech, isAuthenticated: true, accessToken: token, error: null }),

      setTokens: (access, refresh) =>
        set({ accessToken: access, refreshToken: refresh }),

      logout: () =>
        set({
          technician: null,
          isAuthenticated: false,
          accessToken: null,
          refreshToken: null,
          error: null,
        }),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'technician-auth',
      // persist infers the persisted-state type from `partialize` (a 4-field
      // subset of AuthState). Our adapter is a shape-agnostic JSON serializer
      // typed as PersistStorage<AuthState>, so cast it to the inferred subset
      // type — the runtime serialization is identical either way.
      storage: getStorageAdapter() as unknown as PersistStorage<
        Pick<AuthState, 'technician' | 'isAuthenticated' | 'accessToken' | 'refreshToken'>
      >,
      partialize: (state) => ({
        technician: state.technician,
        isAuthenticated: state.isAuthenticated,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);
