/**
 * Technician Auth Store — Zustand
 *
 * Manages technician authentication state.
 * Uses expo-secure-store for native builds and localStorage for web/PWA.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface TechnicianProfile {
  id: string
  name: string
  email: string
  phone?: string
  role: string
  zone?: string
}

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
      storage: getStorageAdapter(),
      partialize: (state) => ({
        technician: state.technician,
        isAuthenticated: state.isAuthenticated,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);
