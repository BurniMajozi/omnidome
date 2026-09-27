-- Talent & Compliance Enhancement Migration
-- Adds reporting lines (manager_id), commission product/dept rules, knowledge base full-text search, and payslip statutory columns

-- 1. Employees reporting line & compliance info
ALTER TABLE employees ADD COLUMN IF NOT EXISTS manager_id UUID REFERENCES employees(id) ON DELETE SET NULL;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS id_number VARCHAR(30);
ALTER TABLE employees ADD COLUMN IF NOT EXISTS tax_number VARCHAR(30);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);

-- 2. Knowledge Base enhancements
ALTER TABLE knowledge_base ALTER COLUMN is_published SET DEFAULT true;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_kb_content_trgm ON knowledge_base USING gin (lower(content) gin_trgm_ops);

-- 3. Commission tiers / rules enhancement
ALTER TABLE commission_tiers ADD COLUMN IF NOT EXISTS product_name VARCHAR(100) DEFAULT 'All Products';
ALTER TABLE commission_tiers ADD COLUMN IF NOT EXISTS department VARCHAR(100) DEFAULT 'Sales';
ALTER TABLE commission_tiers ADD COLUMN IF NOT EXISTS min_threshold_zar NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE commission_tiers ADD COLUMN IF NOT EXISTS description TEXT;

-- 4. Commissions ledger enhancement
ALTER TABLE commissions ADD COLUMN IF NOT EXISTS employee_id UUID REFERENCES employees(id) ON DELETE SET NULL;
ALTER TABLE commissions ADD COLUMN IF NOT EXISTS product_name VARCHAR(100);
ALTER TABLE commissions ADD COLUMN IF NOT EXISTS deal_name VARCHAR(200);

-- 5. Payslips breakdown enhancement
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS basic_salary NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS commission NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS allowances NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS sdl NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS uif_employer NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS tax_rebate NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS annual_taxable NUMERIC(14,2) DEFAULT 0.00;
ALTER TABLE payslips ADD COLUMN IF NOT EXISTS breakdown_json JSONB DEFAULT '{}'::jsonb;

-- Populate default knowledge base articles if empty
INSERT INTO knowledge_base (id, tenant_id, title, category, tags, content, is_published)
SELECT 
    'a0000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'BCEA South Africa Leave & Hours Policy',
    'Compliance & Labor',
    ARRAY['BCEA', 'Leave', 'South Africa', 'Compliance'],
    '# Basic Conditions of Employment Act (BCEA) Guidelines

## 1. Annual Leave Entitlement
- All full-time employees are entitled to **21 consecutive days** (or 15 working days) paid annual leave per 12-month cycle.
- Leave accumulates at the rate of 1 day for every 17 days worked or 1.25 days per month.

## 2. Sick Leave
- During every 36-month sick leave cycle, an employee is entitled to paid sick leave equal to the number of days they would normally work in a 6-week period (typically 30 or 36 days).
- Medical certificate is required if absent for more than 2 consecutive days or on more than 2 occasions in an 8-week period.

## 3. Working Hours & Overtime
- Normal maximum working hours: **45 hours per week** (9 hours/day for 5 days or less; 8 hours/day for more than 5 days).
- Overtime is limited to maximum 10 hours per week and compensated at **1.5x regular wage** or 2.0x for Sundays/Public Holidays.',
    true
WHERE NOT EXISTS (SELECT 1 FROM knowledge_base WHERE id = 'a0000000-0000-0000-0000-000000000001'::uuid);

INSERT INTO knowledge_base (id, tenant_id, title, category, tags, content, is_published)
SELECT 
    'a0000000-0000-0000-0000-000000000002'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'South African Statutory Payroll & SARS PAYE Guide',
    'Finance & Payroll',
    ARRAY['SARS', 'PAYE', 'UIF', 'SDL', 'Tax'],
    '# South African Statutory Payroll Deductions Guide

## 1. SARS PAYE (Pay-As-You-Earn)
- Progressive income tax brackets ranging from 18% to 45%.
- Annual primary rebate: **R17,235** (reduces tax payable).
- Calculated on monthly remuneration annualized: `(Annual Tax - Rebate) / 12`.

## 2. UIF (Unemployment Insurance Fund)
- **Employee contribution**: 1% of gross remuneration capped at **R177.12 / month** (statutory ceiling: R17,712).
- **Employer contribution**: 1% matching contribution (max R177.12 / month).
- Total UIF remittance: 2% of remuneration up to ceiling.

## 3. SDL (Skills Development Levy)
- **Employer contribution**: 1% of total leviable payroll amount.
- Payable if total annual payroll exceeds R500,000.
- Used to fund SETA workplace training grants.',
    true
WHERE NOT EXISTS (SELECT 1 FROM knowledge_base WHERE id = 'a0000000-0000-0000-0000-000000000002'::uuid);

INSERT INTO knowledge_base (id, tenant_id, title, category, tags, content, is_published)
SELECT 
    'a0000000-0000-0000-0000-000000000003'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Sales Commission & Incentives Scheme (ISP & Guarding)',
    'Sales & Commercial',
    ARRAY['Commission', 'Sales', 'Targets', 'Incentives'],
    '# OmniDome Sales Commission Policy

## Commission Tiers & Products
- **Fiber Home (FTTH)**: 8% on first-year contracted monthly revenue after activation.
- **Enterprise Dark Fiber & Dedicated Internet**: 12% on signed 24/36-month enterprise SLAs.
- **VoIP Cloud PBX**: 10% on recurring seat licenses.
- **Guarding & Armed Response SLAs**: 6% recurring commission for contract duration.

## Claim & Payout Journey
1. Sales rep logs signed order and deal value in CRM.
2. Deal reaches `CLOSED_WON` status and passes Finance credit verification.
3. Rep claims commission in Talent Dome -> automatically routed into the next monthly Payroll run as an approved bonus.',
    true
WHERE NOT EXISTS (SELECT 1 FROM knowledge_base WHERE id = 'a0000000-0000-0000-0000-000000000003'::uuid);

-- Populate sample commission tiers if empty
INSERT INTO commission_tiers (id, tenant_id, tier_name, product_name, department, min_deals, max_deals, rate_percent, min_threshold_zar, is_active, sort_order)
SELECT
    'c0000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Fiber Home Standard',
    'Fiber Home (FTTH)',
    'Sales',
    0, 20, 8.00, 0.00, true, 1
WHERE NOT EXISTS (SELECT 1 FROM commission_tiers WHERE id = 'c0000000-0000-0000-0000-000000000001'::uuid);

INSERT INTO commission_tiers (id, tenant_id, tier_name, product_name, department, min_deals, max_deals, rate_percent, min_threshold_zar, is_active, sort_order)
SELECT
    'c0000000-0000-0000-0000-000000000002'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Enterprise Dedicated Bandwidth',
    'Enterprise Leased Line',
    'Sales',
    0, 10, 12.00, 15000.00, true, 2
WHERE NOT EXISTS (SELECT 1 FROM commission_tiers WHERE id = 'c0000000-0000-0000-0000-000000000002'::uuid);

INSERT INTO commission_tiers (id, tenant_id, tier_name, product_name, department, min_deals, max_deals, rate_percent, min_threshold_zar, is_active, sort_order)
SELECT
    'c0000000-0000-0000-0000-000000000003'::uuid,
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Field Tech Router Upsell',
    'Wi-Fi 6 Mesh Hardware',
    'Technicians',
    0, 50, 5.00, 0.00, true, 3
WHERE NOT EXISTS (SELECT 1 FROM commission_tiers WHERE id = 'c0000000-0000-0000-0000-000000000003'::uuid);
