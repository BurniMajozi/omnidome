/**
 * Auth Store — Zustand
 * Manages customer authentication state.
 *
 * Tokens are now stored in Zustand state (not just inside the ApiClient)
 * so they can be forwarded to the orchestrator and other services.
 *
 * Storage strategy:
 *   - Native Expo: expo-secure-store (encrypted)
 *   - Web / PWA: Zustand's default localStorage adapter
 *
 * The ApiClient singleton is kept in sync via setTokens() so existing
 * code that calls api.* methods continues to work unchanged.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api, ApiError } from "./client";
import type { CustomerProfile } from "./types";

// ── Platform-aware storage adapter ────────────────────────────────────────

const getStorageAdapter = () => {
  try {
    const SecureStore = require("expo-secure-store");
    if (typeof window === "undefined") {
      return {
        getItem: async (name: string) => (await SecureStore.getItemAsync(name)) ?? null,
        setItem: (name: string, value: string) => SecureStore.setItemAsync(name, value),
        removeItem: (name: string) => SecureStore.deleteItemAsync(name),
      };
    }
  } catch {
    // expo-secure-store not available — fall through to localStorage
  }
  return undefined;
};

// ── State shape ───────────────────────────────────────────────────────────

interface AuthState {
  customer: CustomerProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  /** JWT access token — available to components that need to call services directly */
  accessToken: string | null;
  /** Refresh token — kept for silent re-auth */
  refreshToken: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (data: Record<string, unknown>) => Promise<void>;
  logout: () => Promise<void>;
  /** Called internally when the ApiClient silently refreshes the access token */
  setTokens: (access: string | null, refresh: string | null) => void;
  clearError: () => void;
}

// ── Store ─────────────────────────────────────────────────────────────────

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      customer: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      accessToken: null,
      refreshToken: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          const result = await api.login(email, password);
          api.setTokens(result.accessToken, result.refreshToken);
          set({
            customer: result.customer,
            isAuthenticated: true,
            isLoading: false,
            accessToken: result.accessToken,
            refreshToken: result.refreshToken,
          });
        } catch (err) {
          set({ error: err instanceof ApiError ? err.message : "Login failed", isLoading: false });
          throw err;
        }
      },

      register: async (data) => {
        set({ isLoading: true, error: null });
        try {
          const result = await api.register(data as Parameters<typeof api.register>[0]);
          api.setTokens(result.accessToken, result.refreshToken);
          set({
            customer: result.customer,
            isAuthenticated: true,
            isLoading: false,
            accessToken: result.accessToken,
            refreshToken: result.refreshToken,
          });
        } catch (err) {
          set({ error: err instanceof ApiError ? err.message : "Registration failed", isLoading: false });
          throw err;
        }
      },

      logout: async () => {
        try {
          await api.logout();
        } finally {
          api.clearAuth();
          set({
            customer: null,
            isAuthenticated: false,
            accessToken: null,
            refreshToken: null,
            error: null,
          });
        }
      },

      setTokens: (access, refresh) => {
        if (access) api.setTokens(access, refresh ?? "");
        set({ accessToken: access, refreshToken: refresh });
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: "customer-auth",
      storage: getStorageAdapter(),
      partialize: (state) => ({
        customer: state.customer,
        isAuthenticated: state.isAuthenticated,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
      onRehydrateStorage: () => (state) => {
        // Re-sync ApiClient after Zustand rehydrates from storage on page load
        if (state?.accessToken) {
          api.setTokens(state.accessToken, state.refreshToken ?? "");
        }
      },
    },
  ),
);
