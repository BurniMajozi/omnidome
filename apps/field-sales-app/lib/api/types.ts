"use client";

/**
 * Mobile Field Sales API types.
 * Aggregates data from CRM, Sales, Billing, Inventory, Communication services.
 */

export interface MobileContact {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  physical_address: string;
  rica_verified: boolean;
  status?: string;
}

export interface MobileDeal {
  id: string;
  name: string;
  customer_id: string;
  stage_name: string;
  value_zar: number;
  status: string;
  close_date?: string;
  created_at: string;
}

export interface MobileLead {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  source: string;
  status: string;
  interest_level: number;
  address: string;
}

export interface MobileQuote {
  id: string;
  deal_id?: string;
  customer_id: string;
  total_monthly: number;
  total_once_off: number;
  status: string;
  valid_until?: string;
  created_at: string;
}

export interface MobileInvoice {
  id: string;
  invoice_number: string;
  amount: number;
  total_amount: number;
  status: string;
  due_date: string;
}

export interface MobileCommission {
  id: string;
  deal_id: string;
  amount_zar: number;
  rate_percent: number;
  status: string;
  created_at: string;
}

export interface Customer360 {
  id: string;
  tenant_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  id_number?: string;
  physical_address: string;
  province: string;
  account_number: string;
  status: string;
  rica_verified: boolean;
  created_at: string;
  updated_at: string;
  tags: string[];
  notes_count: number;
  billing: Array<{ id: string; invoice_number: string; amount: number; total_amount: number; status: string; due_date: string }>;
  support: Array<{ id: string; subject: string; status: string; priority: string }>;
  network: Array<{ id: string; status: string; fno_reference: string }>;
  lifecycle_data: {
    current_stage?: string;
    health_score?: number;
    churn_probability?: number;
    history?: Array<{ stage: string; entered_at: string }>;
  } | null;
}
