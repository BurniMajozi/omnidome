/**
 * API Client for OmniDome Customer Portal
 *
 * Handles:
 * - JWT auth (access + refresh tokens)
 * - Tenant context (X-Tenant-ID header)
 * - Request/response interceptors
 * - Error handling with automatic token refresh
 * - Environment-aware base URL (works in web PWA and native Expo builds)
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'http://localhost:8000';

export interface ApiResponse<T> {
  data: T;
  status: number;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

class ApiClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private tenantId: string | null = null;

  setTokens(access: string, refresh: string) {
    this.accessToken = access;
    this.refreshToken = refresh;
  }

  setTenant(tenantId: string) {
    this.tenantId = tenantId;
  }

  clearAuth() {
    this.accessToken = null;
    this.refreshToken = null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }
    if (this.tenantId) {
      headers['X-Tenant-ID'] = this.tenantId;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401 && this.refreshToken) {
      // Attempt token refresh
      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        return this.request(endpoint, options);
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }));
      throw new ApiError(error.message || 'Request failed', response.status);
    }

    return response.json();
  }

  private async refreshAccessToken(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken: this.refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      this.accessToken = data.accessToken;
      this.refreshToken = data.refreshToken || this.refreshToken;
      return true;
    } catch {
      return false;
    }
  }

  // Auth
  async login(email: string, password: string) {
    return this.request<{ accessToken: string; refreshToken: string; customer: CustomerProfile }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async register(data: RegisterRequest) {
    return this.request<{ accessToken: string; refreshToken: string; customer: CustomerProfile }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async logout() {
    return this.request('/auth/logout', { method: 'POST' });
  }

  // Dashboard
  async getDashboard() {
    return this.request<DashboardData>('/portal/dashboard');
  }

  // Billing
  async getInvoices(params?: { page?: number; status?: string }) {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<PaginatedResponse<Invoice>>(`/billing/invoices${qs ? '?' + qs : ''}`);
  }

  async getInvoice(id: string) {
    return this.request<Invoice>(`/billing/invoices/${id}`);
  }

  async getPayments(params?: { page?: number }) {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<PaginatedResponse<Payment>>(`/billing/payments${qs ? '?' + qs : ''}`);
  }

  async downloadStatement(invoiceId: string) {
    return this.request<{ downloadUrl: string }>(`/billing/invoices/${invoiceId}/statement`);
  }

  async downloadProofOfPayment(paymentId: string) {
    return this.request<{ downloadUrl: string }>(`/billing/payments/${paymentId}/pop`);
  }

  async setupDebitOrder(data: DebitOrderSetup) {
    return this.request('/billing/debit-orders', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Usage
  async getUsage(params?: { from?: string; to?: string }) {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<UsageData>(`/portal/usage${qs ? '?' + qs : ''}`);
  }

  // Support
  async getTickets(params?: { page?: number; status?: string }) {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<PaginatedResponse<SupportTicket>>(`/support/tickets${qs ? '?' + qs : ''}`);
  }

  async getTicket(id: string) {
    return this.request<SupportTicket>(`/support/tickets/${id}`);
  }

  async createTicket(data: CreateTicketRequest) {
    return this.request<SupportTicket>('/support/tickets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async addTicketComment(ticketId: string, message: string) {
    return this.request(`/support/tickets/${ticketId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  }

  // Store
  async getProducts(params?: { category?: string; type?: string; search?: string; page?: number }) {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<PaginatedResponse<StoreProduct>>(`/store/products${qs ? '?' + qs : ''}`);
  }

  async getProduct(id: string) {
    return this.request<StoreProduct>(`/store/products/${id}`);
  }

  async getCart() {
    return this.request<ShoppingCart>('/store/cart');
  }

  async addToCart(productId: string, quantity: number = 1) {
    return this.request<ShoppingCart>('/store/cart/items', {
      method: 'POST',
      body: JSON.stringify({ productId, quantity }),
    });
  }

  async updateCartItem(itemId: string, quantity: number) {
    return this.request<ShoppingCart>(`/store/cart/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify({ quantity }),
    });
  }

  async removeCartItem(itemId: string) {
    return this.request(`/store/cart/items/${itemId}`, { method: 'DELETE' });
  }

  async applyPromoCode(code: string) {
    return this.request<ShoppingCart>(`/store/cart/apply-promo?promoCode=${encodeURIComponent(code)}`, {
      method: 'POST',
    });
  }

  async checkout(data: CheckoutRequest) {
    return this.request<{ orderId: string; orderNumber: string }>('/store/cart/checkout', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Profile
  async getProfile() {
    return this.request<CustomerProfile>('/portal/profile');
  }

  async updateProfile(data: Partial<CustomerProfile>) {
    return this.request<CustomerProfile>('/portal/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getAddresses() {
    return this.request<CustomerAddress[]>('/portal/addresses');
  }

  async addAddress(data: Omit<CustomerAddress, 'id'>) {
    return this.request<CustomerAddress>('/portal/addresses', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getRicaStatus() {
    return this.request<RicaStatus>('/portal/rica/status');
  }

  async submitRicaVerification(data: RicaSubmission) {
    return this.request('/portal/rica/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Referrals
  async getReferralInfo() {
    return this.request<ReferralInfo>('/portal/referrals');
  }

  async getReferralHistory() {
    return this.request<ReferralRecord[]>('/portal/referrals/history');
  }

  // Notifications
  async getNotifications(params?: { page?: number; unreadOnly?: boolean }) {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return this.request<PaginatedResponse<AppNotification>>(`/portal/notifications${qs ? '?' + qs : ''}`);
  }

  async markNotificationRead(id: string) {
    return this.request(`/portal/notifications/${id}/read`, { method: 'POST' });
  }

  // Journey Engine — Cancel Flow
  async triggerCancel(customerSnapshot: Record<string, any>, cancelReason: string) {
    return this.request<{
      cancel_event_id: string;
      matched: boolean;
      journey?: any;
      offer?: any;
      estimated_cost?: number;
    }>('/api/journey-engine/cancel/trigger', {
      method: 'POST',
      body: JSON.stringify({
        customer_id: customerSnapshot.id || customerSnapshot.customer_id,
        account_number: customerSnapshot.account_number || 'ACC-0001',
        customer_snapshot: customerSnapshot,
        cancel_reason: cancelReason,
        source_channel: 'portal',
      }),
    });
  }

  async respondToCancel(cancelEventId: string, decision: 'accept' | 'reject') {
    return this.request('/api/journey-engine/cancel/respond', {
      method: 'POST',
      body: JSON.stringify({
        cancel_event_id: cancelEventId,
        decision,
      }),
    });
  }
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export const api = new ApiClient();
