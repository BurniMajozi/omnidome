/**
 * Auth Store — Zustand
 * Manages customer authentication state
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api, ApiError } from './client';
import type { CustomerProfile } from './types';

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
      partialize: (state) => ({ customer: state.customer, isAuthenticated: state.isAuthenticated }),
    }
  )
);
