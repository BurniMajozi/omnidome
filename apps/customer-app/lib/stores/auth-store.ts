/**
 * Auth Store — Zustand
 * Manages customer authentication state
 *
 * Uses expo-secure-store for native builds and localStorage for web/PWA.
 * The storage adapter is selected at runtime based on platform detection.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api, ApiError } from './client';
import type { CustomerProfile } from './types';

// Platform-aware storage adapter
// On native (Expo), uses SecureStore. On web/PWA, uses localStorage.
const getStorageAdapter = () => {
  try {
    // Check if we're in a native Expo environment
    const SecureStore = require('expo-secure-store');
    const hasWindow = typeof window !== 'undefined';

    if (!hasWindow) {
      // Native-only environment (no WebView)
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

  // Web / PWA fallback — use localStorage via Zustand's default storage
  return undefined; // Let Zustand use its default localStorage storage
};

interface AuthState {
  customer: CustomerProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (data: any) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      customer: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          const result = await api.login(email, password);
          api.setTokens(result.accessToken, result.refreshToken);
          set({ customer: result.customer, isAuthenticated: true, isLoading: false });
        } catch (err) {
          const message = err instanceof ApiError ? err.message : 'Login failed';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      register: async (data) => {
        set({ isLoading: true, error: null });
        try {
          const result = await api.register(data);
          api.setTokens(result.accessToken, result.refreshToken);
          set({ customer: result.customer, isAuthenticated: true, isLoading: false });
        } catch (err) {
          const message = err instanceof ApiError ? err.message : 'Registration failed';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      logout: async () => {
        try {
          await api.logout();
        } finally {
          api.clearAuth();
          set({ customer: null, isAuthenticated: false, error: null });
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'customer-auth',
      storage: getStorageAdapter(),
      partialize: (state) => ({ customer: state.customer, isAuthenticated: state.isAuthenticated }),
    }
  )
);
