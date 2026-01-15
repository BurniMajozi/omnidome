-- CoreConnect Master Database Schema
-- Focus: Multi-tenancy, Smart CRM, and Foundation for Billing/Network Connect

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. TENANCY & IAM
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    subdomain TEXT UNIQUE NOT NULL,
    tier TEXT DEFAULT 'FREE', -- FREE, STARTER, PROFESSIONAL, ENTERPRISE
    vat_number TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role TEXT DEFAULT 'USER', -- ADMIN, MANAGER, AGENT, READ_ONLY
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. SMART CRM (CORE)
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    id_number TEXT, -- South African ID for RICA
    email TEXT,
    phone TEXT,
    physical_address TEXT,
    rica_verified BOOLEAN DEFAULT FALSE,
    opt_in_marketing BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. PRODUCT CATALOG (BILLING FOUNDATION)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    fno_type TEXT, -- Openserve, Vumatel, etc.
    monthly_price DECIMAL(12, 2) NOT NULL,
    setup_fee DECIMAL(12, 2) DEFAULT 0.00,
    tier_level TEXT, -- Starter, Pro, etc.
    is_active BOOLEAN DEFAULT TRUE
);

-- 4. SERVICE INSTANCES (NETWORK FOUNDATION)
CREATE TABLE services (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    product_id UUID REFERENCES products(id),
    status TEXT DEFAULT 'PENDING', -- PENDING, ACTIVE, SUSPENDED, TERMINATED
    fno_reference TEXT,
    installation_date DATE,
    activation_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. SALES & PIPELINE MANAGEMENT
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    source TEXT, -- Website, Referral, Cold Call
    status TEXT DEFAULT 'NEW', -- NEW, QUALIFIED, UNQUALIFIED, CONVERTED
    address TEXT,
    interest_level INTEGER DEFAULT 1, -- 1-5
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipelines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE
);

CREATE TABLE deal_stages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pipeline_id UUID REFERENCES pipelines(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    probability INTEGER DEFAULT 10,
    sort_order INTEGER NOT NULL
);

CREATE TABLE deals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    stage_id UUID REFERENCES deal_stages(id),
    name TEXT NOT NULL,
    amount DECIMAL(12, 2),
    close_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    contact_id UUID REFERENCES contacts(id),
    deal_id UUID REFERENCES deals(id),
    subject TEXT NOT NULL,
    due_date TIMESTAMP WITH TIME ZONE,
    status TEXT DEFAULT 'TODO', -- TODO, IN_PROGRESS, DONE
    priority TEXT DEFAULT 'MEDIUM' -- LOW, MEDIUM, HIGH
);

-- 6. BILLING & SUBSCRIPTIONS
CREATE TABLE billing_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    price DECIMAL(12, 2) NOT NULL,
    currency TEXT DEFAULT 'ZAR',
    billing_cycle TEXT DEFAULT 'MONTHLY', -- MONTHLY, QUARTERLY, ANNUAL
    fno_provider TEXT, -- Openserve, Vumatel, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    plan_id UUID REFERENCES billing_plans(id),
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, SUSPENDED, CANCELLED
    start_date DATE NOT NULL,
    next_billing_date DATE,
    cancel_date DATE,
    paystack_customer_token TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    subscription_id UUID REFERENCES subscriptions(id),
    invoice_number TEXT UNIQUE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    tax_amount DECIMAL(12, 2) NOT NULL, -- 15% VAT
    total_amount DECIMAL(12, 2) NOT NULL,
    status TEXT DEFAULT 'DRAFT', -- DRAFT, SENT, PAID, OVERDUE, REFUNDED
    due_date DATE,
    paid_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    invoice_id UUID REFERENCES invoices(id),
    amount DECIMAL(12, 2) NOT NULL,
    gateway TEXT DEFAULT 'PAYSTACK',
    reference TEXT UNIQUE, -- Paystack Ref
    status TEXT, -- SUCCESS, FAILED
    meta JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE refunds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    payment_id UUID REFERENCES payments(id),
    invoice_id UUID REFERENCES invoices(id),
    amount DECIMAL(12, 2) NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'PENDING', -- PENDING, COMPLETED, FAILED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. RICA & COMPLIANCE (SMILE ID)
CREATE TABLE rica_verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    job_id TEXT UNIQUE NOT NULL, -- Local Job ID
    smile_job_id TEXT, -- Smile ID specific Job ID
    verification_type TEXT NOT NULL, -- SMART_SELFIE, DOCUMENT_VERIFICATION
    status TEXT DEFAULT 'PENDING', -- PENDING, COMPLETED, FAILED, RETRY
    result_code TEXT,
    result_message TEXT,
    full_response JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE nas (
    id SERIAL PRIMARY KEY,
    nasname TEXT NOT NULL, -- IP or FQDN of the Router/BNG
    shortname TEXT,
    fno_id UUID REFERENCES fno_portals(id), -- Link NAS to an FNO region
    type TEXT DEFAULT 'Mikrotik',
    secret TEXT NOT NULL,
    description TEXT DEFAULT 'ISP Core Router'
);

CREATE TABLE radius_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    subscription_id UUID REFERENCES subscriptions(id),
    device_id UUID REFERENCES iot_devices(id), -- Link to specific ONT/Router hardware
    username TEXT UNIQUE NOT NULL, -- PPPoE/IPOE Username
    password TEXT NOT NULL,
    static_ip INET,
    profile_name TEXT, -- Link to radgroupreply for speed profiles
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, SUSPENDED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE radcheck (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '==',
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_radcheck_username ON radcheck(username);

CREATE TABLE radreply (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '=',
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_radreply_username ON radreply(username);

CREATE TABLE radgroupcheck (
    id SERIAL PRIMARY KEY,
    groupname TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '==',
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE radgroupreply (
    id SERIAL PRIMARY KEY,
    groupname TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '=',
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE radusergroup (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    groupname TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_radusergroup_username ON radusergroup(username);

CREATE TABLE radacct (
    radacctid BIGSERIAL PRIMARY KEY,
    acctsessionid TEXT NOT NULL DEFAULT '',
    acctuniqueid TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    groupname TEXT NOT NULL DEFAULT '',
    realm TEXT DEFAULT '',
    nasipaddress INET NOT NULL,
    nasportid TEXT DEFAULT NULL,
    nasporttype TEXT DEFAULT NULL,
    acctstarttime TIMESTAMP WITH TIME ZONE,
    acctupdatetime TIMESTAMP WITH TIME ZONE,
    acctstoptime TIMESTAMP WITH TIME ZONE,
    acctinterval INTEGER DEFAULT NULL,
    acctsessiontime BIGINT DEFAULT NULL,
    acctauthentic TEXT DEFAULT NULL,
    connectinfo_start TEXT DEFAULT NULL,
    connectinfo_stop TEXT DEFAULT NULL,
    acctinputoctets BIGINT DEFAULT NULL,
    acctoutputoctets BIGINT DEFAULT NULL,
    calledstationid TEXT DEFAULT NULL,
    callingstationid TEXT DEFAULT NULL,
    acctterminatecause TEXT DEFAULT NULL,
    servicetype TEXT DEFAULT NULL,
    framedprotocol TEXT DEFAULT NULL,
    framedipaddress INET DEFAULT NULL
);
CREATE INDEX idx_radacct_username ON radacct(username);
CREATE INDEX idx_radacct_active ON radacct(acctstoptime) WHERE acctstoptime IS NULL;

CREATE TABLE radpostauth (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    pass TEXT,
    reply TEXT,
    authdate TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE fno_portals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    fno_name TEXT NOT NULL, -- Openserve, Vumatel, etc.
    portal_url TEXT,
    username TEXT,
    password_encrypted TEXT,
    meta JSONB, -- For specific automation fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE automation_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL, -- FNO_AVAILABILITY, FNO_ORDER, FNO_CANCELLATION
    fno_name TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, COMPLETED, FAILED
    payload JSONB, -- Input data
    result JSONB, -- Automation output
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. IOT & SMART HOME MANAGEMENT
CREATE TABLE iot_devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id),
    device_name TEXT NOT NULL,
    device_type TEXT NOT NULL, -- ONT, ROUTER, SMART_BULB, SENSOR
    mac_address TEXT UNIQUE,
    serial_number TEXT UNIQUE,
    status TEXT DEFAULT 'OFFLINE', -- ONLINE, OFFLINE, MAINTENANCE
    firmware_version TEXT,
    last_seen TIMESTAMP WITH TIME ZONE,
    metadata JSONB, -- Custom device config
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ont_signal_history (
    id BIGSERIAL PRIMARY KEY,
    device_id UUID REFERENCES iot_devices(id) ON DELETE CASCADE,
    rx_power_dbm DECIMAL(5,2) NOT NULL, -- Received Optical Power (standard: -8 to -28 dBm)
    tx_power_dbm DECIMAL(5,2), -- Transmit Optical Power
    voltage_v DECIMAL(5,2),
    bias_current_ma DECIMAL(5,2),
    temperature_c DECIMAL(5,2),
    measured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ont_signal_device_time ON ont_signal_history(device_id, measured_at DESC);

CREATE TABLE fiber_health_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    device_id UUID REFERENCES iot_devices(id),
    severity TEXT NOT NULL, -- WARNING, CRITICAL
    issue_type TEXT, -- SIGNAL_DEGRADATION, POWER_LOSS, MAC_FLAPPING
    current_value TEXT,
    is_proactive BOOLEAN DEFAULT TRUE,
    ticket_id UUID REFERENCES tickets(id),
    status TEXT DEFAULT 'OPEN', -- OPEN, ACKNOWLEDGED, RESOLVED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE iot_commands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id UUID REFERENCES iot_devices(id) ON DELETE CASCADE,
    command_type TEXT NOT NULL, -- REBOOT, FIRMWARE_UPDATE, TOGGLE_POWER
    payload JSONB,
    status TEXT DEFAULT 'PENDING', -- PENDING, SENT, EXECUTED, FAILED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 10. STOCK & INVENTORY MANAGEMENT
CREATE TABLE product_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, -- IOT, Network, Promo, etc.
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    category_id UUID REFERENCES product_categories(id),
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    cost_price DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    rrp DECIMAL(12,2) NOT NULL DEFAULT 0.00, -- Recommended Retail Price
    margin_percent DECIMAL(5,2) GENERATED ALWAYS AS (
        CASE WHEN rrp > 0 THEN ((rrp - cost_price) / rrp) * 100 ELSE 0 END
    ) STORED,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE warehouses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, -- Main WH, Service Van 1, China Factory, Partner Warehouse
    location TEXT,
    is_external BOOLEAN DEFAULT FALSE,
    partner_name TEXT, -- For external 3PL partners
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shipments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    origin_warehouse_id UUID REFERENCES warehouses(id),
    destination_warehouse_id UUID REFERENCES warehouses(id),
    status TEXT DEFAULT 'ORDERED', -- ORDERED, IN_TRANSIT_SEA, IN_TRANSIT_AIR, AT_PORT, DELIVERED
    tracking_number TEXT,
    eta TIMESTAMP WITH TIME ZONE,
    ata TIMESTAMP WITH TIME ZONE, -- Actual Time of Arrival
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shipment_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shipment_id UUID REFERENCES shipments(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    quantity INTEGER NOT NULL,
    cost_price DECIMAL(12,2) -- Capturing landed cost if different from base cost
);

CREATE TABLE inventory_levels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    warehouse_id UUID REFERENCES warehouses(id),
    product_id UUID REFERENCES products(id),
    soh INTEGER NOT NULL DEFAULT 0, -- Stock On Hand
    sit INTEGER NOT NULL DEFAULT 0, -- Stock In Transit
    allocated INTEGER NOT NULL DEFAULT 0, -- Reserved for orders
    min_threshold INTEGER DEFAULT 10,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(warehouse_id, product_id)
);

CREATE TABLE stock_movements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    from_warehouse_id UUID REFERENCES warehouses(id),
    to_warehouse_id UUID REFERENCES warehouses(id),
    quantity INTEGER NOT NULL,
    movement_type TEXT NOT NULL, -- PURCHASE, TRANSFER, SALE, RETURN_FROM_CUSTOMER, WRITE_OFF
    reference_id UUID, -- Link to Order ID or Return ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales_planning (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    target_month DATE NOT NULL,
    forecast_units INTEGER NOT NULL DEFAULT 0,
    actual_units INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. SUPPORT & TICKETING HUB
CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'NORMAL', -- LOW, NORMAL, HIGH, URGENT
    status TEXT DEFAULT 'OPEN', -- OPEN, IN_PROGRESS, ON_HOLD, CLOSED, REOPENED
    category TEXT, -- Billing, Technical, Sales, RICA
    assigned_to UUID, -- User ID
    external_fno_ref TEXT, -- Reference ID from FNO portal
    fno_id UUID, -- Link to FNO if applicable
    is_fcr BOOLEAN DEFAULT FALSE, -- First Contact Resolution
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE network_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    fno_affected TEXT,
    region_affected TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    notifications_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ticket_replies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_id UUID REFERENCES tickets(id) ON DELETE CASCADE,
    author_id UUID, -- Either User ID or Customer ID
    author_type TEXT NOT NULL, -- STAFF, CUSTOMER
    message TEXT NOT NULL,
    is_private BOOLEAN DEFAULT FALSE, -- Internal staff notes
    automation_log_id UUID, -- Link to Network Hub automation job
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT,
    tags TEXT[],
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 13. HR & STAFF MANAGEMENT
CREATE TABLE employees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL, -- Link to system user if they have access
    employee_id TEXT UNIQUE NOT NULL, -- Internal ID (e.g. STF-001)
    full_name TEXT NOT NULL,
    job_title TEXT NOT NULL,
    department TEXT NOT NULL, -- Support, Sales, Network, HR, Admin
    hire_date DATE NOT NULL,
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, ON_LEAVE, TERMINATED
    profile_photo_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE onboarding_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    task_name TEXT NOT NULL,
    is_completed BOOLEAN DEFAULT FALSE,
    due_date DATE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE training_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    course_name TEXT NOT NULL,
    certification_earned TEXT,
    expiry_date DATE,
    completion_date DATE NOT NULL,
    grade TEXT
);

CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tickets_resolved INTEGER DEFAULT 0,
    avg_resolution_time_minutes INTEGER DEFAULT 0,
    fcr_rate DECIMAL(5,2) DEFAULT 0.00,
    nps_score DECIMAL(5,2) DEFAULT 0.00,
    kpi_score DECIMAL(5,2) DEFAULT 0.00, -- Aggregate HR score (1-10)
    manager_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE disciplinary_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    case_type TEXT NOT NULL, -- VERBAL_WARNING, WRITTEN_WARNING, FINAL_WARNING, HEARING
    description TEXT NOT NULL,
    consequence TEXT,
    case_date DATE NOT NULL,
    status TEXT DEFAULT 'OPEN', -- OPEN, CLOSED, APPEALED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE staff_sentiment_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    sentiment_score DECIMAL(3,2) NOT NULL, -- 0 (Neg) to 1 (Pos)
    detected_keywords TEXT[],
    attrition_risk_level TEXT DEFAULT 'LOW', -- LOW, MEDIUM, HIGH
    analysis_date DATE DEFAULT CURRENT_DATE,
    source_type TEXT -- INTERNAL_NOTES, PERFORMANCE_REVIEW, PEER_FEEDBACK
);

CREATE TABLE exit_interviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    reason_for_leaving TEXT,
    feedback_on_management TEXT,
    would_recommend BOOLEAN,
    exit_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 13. AUDIT LOGGING (SECURITY)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id UUID,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Sales performance
CREATE INDEX idx_leads_tenant ON leads(tenant_id);
CREATE INDEX idx_deals_stage ON deals(stage_id);
CREATE INDEX idx_tasks_delegate ON tasks(user_id);
CREATE INDEX idx_contacts_tenant ON contacts(tenant_id);
CREATE INDEX idx_services_contact ON services(contact_id);
CREATE INDEX idx_audit_tenant ON audit_logs(tenant_id);
