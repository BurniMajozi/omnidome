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

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

import type {
  TechJob,
  TechDevice,
  TechInventoryItem,
  SpeedTestResult,
  JobCompletionData,
  TechStats,
  DeviceSignal,
  RadiusAccount,
} from './types';

export const technicianApi = {
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

  // SSE stream for real-time job dispatch
  streamJobEvents: (onEvent: (event: { event: string; data: unknown }) => void) => {
    const evtSource = new EventSource('/api/support/technicians/me/stream');
    evtSource.addEventListener('connected', (e) => {
      onEvent({ event: 'connected', data: JSON.parse(e.data as string) });
    });
    evtSource.addEventListener('initial_state', (e) => {
      onEvent({ event: 'initial_state', data: JSON.parse(e.data as string) });
    });
    evtSource.addEventListener('new_ticket', (e) => {
      onEvent({ event: 'new_ticket', data: JSON.parse(e.data as string) });
    });
    evtSource.addEventListener('ticket_update', (e) => {
      onEvent({ event: 'ticket_update', data: JSON.parse(e.data as string) });
    });
    evtSource.addEventListener('ping', () => {
      // Keep-alive, no action needed
    });
    evtSource.onerror = () => {
      onEvent({ event: 'error', data: { message: 'Stream connection lost' } });
    };
    return () => evtSource.close();
  },
};
