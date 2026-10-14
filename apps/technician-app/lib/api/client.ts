/**
 * Technician API Client
 * Aggregates data from Support, Network, IoT, Inventory services.
 *
 * Works in web PWA and native Expo builds via environment-aware base URL.
 */

const API =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'http://localhost:8000';

import type {
  TechJob,
  TechDevice,
  TechInventoryItem,
  SpeedTestResult,
  JobCompletionData,
  TechStats,
  DeviceSignal,
  RadiusAccount,
  TechnicianProfile,
} from './types';

// Lazy import avoids a hard dependency cycle at module init time.
import { useAuthStore } from '../stores/auth-store';

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, {
    cache: 'no-store',
    headers,
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

export const technicianApi = {
  homeDomeRequest: async (path: string, init?: RequestInit) => {
    if (!path.startsWith('/api/iot/homes')) throw new Error('Invalid HomeDome path');
    const send = () => {
      const token = useAuthStore.getState().accessToken;
      return fetch(path.replace('/api/iot/homes', '/api/home-dome'), { ...init, cache: 'no-store', signal: AbortSignal.timeout(60000),
        headers: { 'Content-Type': 'application/json', ...init?.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
    };
    const response = await send();
    const refresh = useAuthStore.getState().refreshToken;
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL, key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (response.status === 401 && refresh && url && key) {
      const refreshed = await fetch(url.replace(/\/$/, '') + '/auth/v1/token?grant_type=refresh_token', {
        method: 'POST', headers: { apikey: key, 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }) });
      const data = await refreshed.json();
      if (refreshed.ok && data.access_token) { useAuthStore.getState().setTokens(data.access_token, data.refresh_token); return send(); }
    }
    return response;
  },
  // Auth
  login: async (email: string, password: string) => {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!url || !key) throw new Error('Technician sign-in needs Supabase configuration');
    const response = await fetch(url.replace(/\/$/, '') + '/auth/v1/token?grant_type=password', {
      method: 'POST', headers: { apikey: key, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();
    if (!response.ok || !data.access_token) throw new Error(data.error_description || data.msg || 'Sign-in failed');
    const profile = await fetch('/api/home-dome/staff-profile', { cache: 'no-store', headers: { Authorization: `Bearer ${data.access_token}` } });
    const technician = await profile.json();
    if (!profile.ok) throw new Error(technician.detail || 'Your account needs an IoT support role');
    return { accessToken: data.access_token as string, refreshToken: data.refresh_token as string,
      technician: technician as TechnicianProfile };
  },

  // Job queue
  getMyJobs: (params?: { status?: string; priority?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.priority) q.set('priority', params.priority);
    return fetchJSON<TechJob[]>(`/api/support/tickets?${q}`);
  },

  getJob: (jobId: string) =>
    fetchJSON<TechJob>(`/api/support/tickets/${jobId}`),

  acceptJob: (jobId: string) =>
    fetchJSON<{ status: string }>(`/api/support/tickets/${jobId}/accept`, { method: 'POST' }),

  startJob: (jobId: string) =>
    fetchJSON<{ status: string }>(`/api/support/tickets/${jobId}/start`, { method: 'POST' }),

  completeJob: (data: JobCompletionData) =>
    fetchJSON<{ status: string; commission_earned?: number }>(`/api/support/tickets/${data.job_id}/resolve`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  escalateJob: (jobId: string, reason: string) =>
    fetchJSON<{ status: string }>(`/api/support/tickets/${jobId}/escalate-fno`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  // Customer devices at site
  getCustomerDevices: (contactId: string) =>
    fetchJSON<TechDevice[]>(`/api/iot/devices?contact_id=${contactId}`),

  getDeviceSignal: (deviceId: string) =>
    fetchJSON<DeviceSignal>(
      `/api/iot/devices/${deviceId}/signal`
    ),

  rebootDevice: (deviceId: string) =>
    fetchJSON<{ status: string }>(`/api/iot/devices/${deviceId}/reboot`, { method: 'POST' }),

  // RADIUS account check
  getRadiusAccount: (contactId: string) =>
    fetchJSON<RadiusAccount>(`/api/network/radius-accounts?contact_id=${contactId}`),

  // Inventory — check parts availability
  checkParts: (sku: string) =>
    fetchJSON<TechInventoryItem[]>(`/api/inventory/stock?sku=${encodeURIComponent(sku)}`),

  checkoutParts: (data: { job_id: string; items: Array<{ product_id: string; quantity: number }> }) =>
    fetchJSON<{ status: string; reference: string }>('/api/inventory/stock/checkout', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Speed test (runs from gateway)
  runSpeedTest: () =>
    fetchJSON<SpeedTestResult>('/api/network/speed-test', { method: 'POST' }),

  // My stats
  getMyStats: () =>
    fetchJSON<TechStats>(`/api/support/technicians/me/stats`),

  // SSE stream for real-time job dispatch.
  // Uses fetch + ReadableStream (not EventSource) so we can send the bearer
  // token and target an absolute API URL — EventSource cannot set auth headers
  // and a relative URL never resolves inside the Expo WebView shell.
  streamJobEvents: (onEvent: (event: { event: string; data: unknown }) => void) => {
    const token = useAuthStore.getState().accessToken;
    const url = `${API}/api/support/technicians/me/stream`;
    const controller = new AbortController();
    let buffer = '';

    const dispatch = (raw: string) => {
      // Parse one SSE event block: `event: <name>\n\ndata: <json>\n\n`
      const match = raw.match(/event:\s*(\S+)\s*\n\s*data:\s*([\s\S]*?)\n\n/);
      if (!match) return;
      const name = match[1];
      if (name === 'ping') return; // keep-alive, no action
      try {
        onEvent({ event: name, data: JSON.parse(match[2]) });
      } catch {
        // Ignore malformed event payloads
      }
    };

    (async () => {
      try {
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          onEvent({ event: 'error', data: { message: `Stream error ${res.status}` } });
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buffer.indexOf('\n\n')) !== -1) {
            const block = buffer.slice(0, idx + 2);
            buffer = buffer.slice(idx + 2);
            dispatch(block);
          }
        }
      } catch (err) {
        if ((err as Error)?.name !== 'AbortError') {
          onEvent({ event: 'error', data: { message: 'Stream connection lost' } });
        }
      }
    })();

    return () => controller.abort();
  },
};
