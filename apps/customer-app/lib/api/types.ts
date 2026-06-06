/**
 * Customer Portal — Shared TypeScript Types
 * Mirrors backend Pydantic models for type-safe API consumption
 */

// ════════════════════════════════════════════════════════════════════════
// AUTH
// ════════════════════════════════════════════════════════════════════════

export interface CustomerProfile {
  id: string;
  email: string;
  phone: string;
  firstName: string;
  lastName: string;
  accountNumber: string;
  idNumber?: string;
  ricaVerified: boolean;
  ricaStatus: 'pending' | 'verified' | 'failed' | 'expired';
  contactChannel: 'sms' | 'whatsapp' | 'email' | 'push';
  package?: string;
  monthlySpend?: number;
  avatarUrl?: string;
  createdAt: string;
}

export interface RegisterRequest {
  email: string;
  phone: string;
  password: string;
  firstName: string;
  lastName: string;
  idNumber: string;
  accountNumber?: string;
}

// ════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ════════════════════════════════════════════════════════════════════════

export interface DashboardData {
  customer: CustomerProfile;
  currentPackage?: {
    name: string;
    speed: string;
    monthlyPrice: number;
    dataCap?: string;
  };
  usageThisMonth: UsageSummary;
  nextBill?: {
    amount: number;
    dueDate: string;
  };
  openTickets: number;
  unreadNotifications: number;
  recentActivity: ActivityItem[];
  quickActions: QuickAction[];
}

export interface UsageSummary {
  downloadGb: number;
  uploadGb: number;
  capGb?: number;
  percentageUsed: number;
  daysRemaining: number;
}

export interface ActivityItem {
  id: string;
  type: string;
  summary: string;
  timestamp: string;
  category: string;
}

export interface QuickAction {
  id: string;
  label: string;
  icon: string;
  href: string;
  color?: string;
}

// ════════════════════════════════════════════════════════════════════════
// BILLING
// ════════════════════════════════════════════════════════════════════════

export interface Invoice {
  id: string;
  number: string;
  status: 'draft' | 'sent' | 'paid' | 'partially_paid' | 'overdue' | 'voided';
  subtotalZar: number;
  vatZar: number;
  totalZar: number;
  amountPaidZar: number;
  dueDate: string;
  billingPeriodStart?: string;
  billingPeriodEnd?: string;
  lineItems?: InvoiceLineItem[];
  createdAt: string;
}

export interface InvoiceLineItem {
  description: string;
  quantity: number;
  unitPriceZar: number;
  totalZar: number;
}

export interface Payment {
  id: string;
  invoiceId?: string;
  amountZar: number;
  method: 'manual' | 'eft' | 'card' | 'debit_order';
  reference?: string;
  status: 'pending' | 'completed' | 'failed' | 'refunded';
  createdAt: string;
}

export interface DebitOrderSetup {
  bankName: string;
  branchCode: string;
  accountHolder: string;
  accountNumber: string;
  accountType: 'cheque' | 'savings' | 'transmission';
  debitDay: number;
  maxAmountZar?: number;
}

// ════════════════════════════════════════════════════════════════════════
// USAGE
// ════════════════════════════════════════════════════════════════════════

export interface UsageData {
  currentPeriod: {
    start: string;
    end: string;
    downloadGb: number;
    uploadGb: number;
    capGb?: number;
    percentageUsed: number;
  };
  dailyUsage: DailyUsagePoint[];
  history: MonthlyUsageSummary[];
  topApps?: { name: string; usageGb: number }[];
}

export interface DailyUsagePoint {
  date: string;
  downloadMb: number;
  uploadMb: number;
}

export interface MonthlyUsageSummary {
  month: string;
  downloadGb: number;
  uploadGb: number;
  capGb?: number;
}

// ════════════════════════════════════════════════════════════════════════
// SUPPORT
// ════════════════════════════════════════════════════════════════════════

export interface SupportTicket {
  id: string;
  ticketNumber: string;
  subject: string;
  description: string;
  status: 'open' | 'in_progress' | 'waiting_customer' | 'resolved' | 'closed';
  priority: 'low' | 'medium' | 'high' | 'critical';
  category: string;
  createdAt: string;
  updatedAt: string;
  lastCommentAt?: string;
}

export interface CreateTicketRequest {
  subject: string;
  description: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  category: string;
  attachmentUrls?: string[];
}

export interface TicketComment {
  id: string;
  message: string;
  authorType: 'customer' | 'agent' | 'system';
  authorName: string;
  createdAt: string;
  attachmentUrls?: string[];
}

// ════════════════════════════════════════════════════════════════════════
// STORE
// ════════════════════════════════════════════════════════════════════════

export interface StoreProduct {
  id: string;
  sku: string;
  name: string;
  slug: string;
  description?: string;
  shortDescription?: string;
  productType: 'hardware' | 'vas' | 'accessory';
  onceOffPriceZar: number;
  monthlyPriceZar: number;
  stockQuantity: number;
  imageUrls: string[];
  specs: Record<string, any>;
  isActive: boolean;
  isFeatured: boolean;
  requiresSubscription: boolean;
  compatiblePackages: string[];
  avgRating?: number;
  reviewCount?: number;
}

export interface ShoppingCart {
  id: string;
  status: string;
  itemCount: number;
  subtotalZar: number;
  discountZar: number;
  totalZar: number;
  promoCode?: string;
  expiresAt?: string;
  items: CartItem[];
}

export interface CartItem {
  id: string;
  productId: string;
  productName?: string;
  productSku?: string;
  productType: string;
  quantity: number;
  unitPriceZar: number;
  totalPriceZar: number;
  targetSubscriptionId?: string;
}

export interface CheckoutRequest {
  serviceAddressId?: string;
  billingAddressId?: string;
  paymentMethodId?: string;
  preferredContactChannel: string;
  contactPhone?: string;
  contactEmail?: string;
  customerNotes?: string;
}

// ════════════════════════════════════════════════════════════════════════
// PROFILE & RICA
// ════════════════════════════════════════════════════════════════════════

export interface CustomerAddress {
  id: string;
  addressType: 'service' | 'physical' | 'billing';
  line1: string;
  line2?: string;
  city: string;
  province?: string;
  postalCode: string;
  gpsLat?: number;
  gpsLng?: number;
  isPrimary: boolean;
}

export interface RicaStatus {
  status: 'pending' | 'verified' | 'failed' | 'expired' | 'manual_review';
  idNumber?: string;
  verifiedAt?: string;
  documentType?: string;
  retryCount: number;
  maxRetries: number;
  nextStep?: string;
}

export interface RicaSubmission {
  documentType: 'south_african_id' | 'passport' | 'smart_id';
  idNumber: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  documentFrontUrl?: string;
  documentBackUrl?: string;
  selfieUrl?: string;
  proofOfAddressUrl?: string;
}

// ════════════════════════════════════════════════════════════════════════
// REFERRALS
// ════════════════════════════════════════════════════════════════════════

export interface ReferralInfo {
  referralCode: string;
  referralLink: string;
  totalReferrals: number;
  activeReferrals: number;
  rewardsEarned: number;
  rewardsPending: number;
  referrerDiscountZar: number;
  refereeDiscountZar: number;
  maxReferrals: number;
}

export interface ReferralRecord {
  id: string;
  referredCustomerName: string;
  referredCustomerEmail: string;
  status: 'pending' | 'active' | 'completed';
  rewardZar: number;
  createdAt: string;
}

// ════════════════════════════════════════════════════════════════════════
// NOTIFICATIONS
// ════════════════════════════════════════════════════════════════════════

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  isRead: boolean;
  actionUrl?: string;
  createdAt: string;
}

// ════════════════════════════════════════════════════════════════════════
// WHITE-LABEL
// ════════════════════════════════════════════════════════════════════════

// ════════════════════════════════════════════════════════════════════════
// A/B TESTING
// ════════════════════════════════════════════════════════════════════════

export interface ABTest {
  id: string;
  tenant_id: string;
  name: string;
  journey_a_id: string;
  journey_b_id: string;
  traffic_split: number;
  status: 'draft' | 'running' | 'paused' | 'completed';
  started_at?: string;
  ended_at?: string;
  winner?: 'a' | 'b';
  created_at: string;
  updated_at: string;
}

export interface ABTestCreate {
  name: string;
  journey_a_id: string;
  journey_b_id: string;
  traffic_split: number;
}

export interface ABTestResults {
  variant_a: { assignments: number; outcomes: number; acceptance_rate: number };
  variant_b: { assignments: number; outcomes: number; acceptance_rate: number };
  winner?: 'a' | 'b';
  confidence?: number;
}

export interface ABTestAssignment {
  id: string;
  ab_test_id: string;
  customer_id: string;
  variant: 'a' | 'b';
  assigned_at: string;
}

// ════════════════════════════════════════════════════════════════════════
// ANALYTICS DASHBOARDS
// ════════════════════════════════════════════════════════════════════════

export interface WidgetConfig {
  type: 'line_chart' | 'bar_chart' | 'kpi_card' | 'table' | 'funnel';
  title: string;
  metric: string;
  config?: Record<string, any>;
}

export interface Dashboard {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  widget_config: WidgetConfig[];
  is_template: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardCreate {
  name: string;
  description?: string;
  widget_config: WidgetConfig[];
}

export interface DashboardTemplate {
  id: string;
  name: string;
  description: string;
  widget_config: WidgetConfig[];
}

export interface RealtimeMetrics {
  active_users?: number;
  conversion_rate?: number;
  revenue_today?: number;
}

export interface BrandConfig {
  appName: string;
  logo: string;
  favicon: string;
  colors: {
    primary: string;
    primaryDark: string;
    secondary: string;
    accent: string;
    background: string;
    surface: string;
    text: string;
    textSecondary: string;
    error: string;
    success: string;
    warning: string;
  };
  fonts: {
    heading: string;
    body: string;
  };
  contact: {
    phone: string;
    email: string;
    website: string;
  };
}

export interface FeatureFlags {
  dashboard: { enabled: boolean };
  billing: { enabled: boolean; invoices: boolean; payments: boolean; statements: boolean; debitOrders: boolean };
  usage: { enabled: boolean; graphs: boolean; capWarnings: boolean };
  support: { enabled: boolean; tickets: boolean; liveChat: boolean; knowledgeBase: boolean };
  store: { enabled: boolean; hardware: boolean; vas: boolean; bundles: boolean; reviews: boolean };
  profile: { enabled: boolean; personalInfo: boolean; addresses: boolean; contactPrefs: boolean };
  rica: { enabled: boolean; documentUpload: boolean; selfieVerification: boolean };
  referrals: { enabled: boolean };
  notifications: { enabled: boolean; push: boolean; sms: boolean; email: boolean };
  offline: { enabled: boolean };
}

// ════════════════════════════════════════════════════════════════════════
// IoT
// ════════════════════════════════════════════════════════════════════════

export interface IoTDevice {
  id: string;
  name: string;
  type: string;
  domain: string;
  manufacturer?: string;
  model?: string;
  firmwareVersion?: string;
  status: 'online' | 'offline' | 'unavailable';
  roomId?: string;
  roomName?: string;
  attributes?: Record<string, any>;
  lastSeen?: string;
  createdAt: string;
}

export interface IoTRoom {
  id: string;
  name: string;
  icon?: string;
  deviceCount: number;
  description?: string;
  createdAt: string;
}

export interface IoTSensorReading {
  id: string;
  sensorId: string;
  sensorName?: string;
  sensorType?: string;
  value: number;
  unit?: string;
  recordedAt: string;
}

export interface IoTScene {
  id: string;
  name: string;
  icon?: string;
  description?: string;
  deviceCount: number;
  isActive: boolean;
  createdAt: string;
}

export interface IoTAlert {
  id: string;
  type: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  deviceId?: string;
  deviceName?: string;
  isRead: boolean;
  createdAt: string;
}

export interface IoTEvent {
  id: string;
  eventType: string;
  deviceId?: string;
  deviceName?: string;
  description: string;
  metadata?: Record<string, any>;
  createdAt: string;
}
