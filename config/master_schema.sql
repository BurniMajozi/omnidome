-- CoreConnect Master Database Schema
-- Focus: Multi-tenancy, Smart CRM, and Foundation for Billing/Network Connect

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Enable trigram search for fast ILIKE searches
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. TENANCY & IAM
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    subdomain TEXT UNIQUE NOT NULL,
    org_code TEXT UNIQUE, -- External organisation identifier (optional but recommended)
    tier TEXT DEFAULT 'FREE', -- FREE, STARTER, PROFESSIONAL, ENTERPRISE
    vat_number TEXT,
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, SUSPENDED, CLOSED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role TEXT DEFAULT 'USER', -- Legacy role field (prefer RBAC tables below)
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 1b. MODULE CATALOG & ENTITLEMENTS
CREATE TABLE modules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    is_core BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tenant_modules (
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'ENABLED', -- ENABLED, DISABLED, TRIAL
    enabled_by UUID REFERENCES users(id),
    enabled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    disabled_at TIMESTAMP WITH TIME ZONE,
    config JSONB,
    PRIMARY KEY (tenant_id, module_id)
);

CREATE INDEX idx_tenant_modules_tenant ON tenant_modules(tenant_id);
CREATE INDEX idx_tenant_modules_module ON tenant_modules(module_id);

-- 1c. ROLE-BASED ACCESS CONTROL (RBAC)
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    scope TEXT NOT NULL, -- PLATFORM, TENANT
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (scope IN ('PLATFORM', 'TENANT')),
    CHECK (
        (scope = 'PLATFORM' AND tenant_id IS NULL) OR
        (scope = 'TENANT' AND tenant_id IS NOT NULL)
    ),
    UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX idx_roles_platform_name ON roles(name) WHERE tenant_id IS NULL;

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE role_permissions (
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id),
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, role_id, tenant_id)
);

CREATE UNIQUE INDEX idx_user_roles_platform ON user_roles(user_id, role_id) WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX idx_user_roles_tenant ON user_roles(user_id, role_id, tenant_id) WHERE tenant_id IS NOT NULL;

CREATE TABLE role_modules (
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
    can_access BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (role_id, module_id)
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
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
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
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    username TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '==',
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_radcheck_username ON radcheck(username);
CREATE INDEX idx_radcheck_tenant_username ON radcheck(tenant_id, username);

CREATE TABLE radreply (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    username TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '=',
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_radreply_username ON radreply(username);
CREATE INDEX idx_radreply_tenant_username ON radreply(tenant_id, username);

CREATE TABLE radgroupcheck (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    groupname TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '==',
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_radgroupcheck_tenant_group ON radgroupcheck(tenant_id, groupname);

CREATE TABLE radgroupreply (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    groupname TEXT NOT NULL DEFAULT '',
    attribute TEXT NOT NULL DEFAULT '',
    op VARCHAR(2) NOT NULL DEFAULT '=',
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_radgroupreply_tenant_group ON radgroupreply(tenant_id, groupname);

CREATE TABLE radusergroup (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    username TEXT NOT NULL DEFAULT '',
    groupname TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_radusergroup_username ON radusergroup(username);
CREATE INDEX idx_radusergroup_tenant_username ON radusergroup(tenant_id, username);

CREATE TABLE radacct (
    radacctid BIGSERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
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
CREATE INDEX idx_radacct_tenant_username ON radacct(tenant_id, username);
CREATE INDEX idx_radacct_active ON radacct(acctstoptime) WHERE acctstoptime IS NULL;

CREATE TABLE radpostauth (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    pass TEXT,
    reply TEXT,
    authdate TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_radpostauth_tenant_username ON radpostauth(tenant_id, username);

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

-- Search acceleration indexes (trigram + lower)
CREATE INDEX IF NOT EXISTS idx_tenants_name_trgm ON tenants USING gin (lower(name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tenants_subdomain_trgm ON tenants USING gin (lower(subdomain) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tenants_org_code_trgm ON tenants USING gin (lower(org_code) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (lower(email));

CREATE INDEX IF NOT EXISTS idx_contacts_first_name_trgm ON contacts USING gin (lower(first_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_last_name_trgm ON contacts USING gin (lower(last_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_email_trgm ON contacts USING gin (lower(email) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_phone_trgm ON contacts USING gin (phone gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_leads_first_name_trgm ON leads USING gin (lower(first_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_last_name_trgm ON leads USING gin (lower(last_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_email_trgm ON leads USING gin (lower(email) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_phone_trgm ON leads USING gin (phone gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_tickets_subject_trgm ON tickets USING gin (lower(subject) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_kb_title_trgm ON knowledge_base USING gin (lower(title) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (lower(name) gin_trgm_ops);

-- 14. MODULES & RBAC SEED DATA
INSERT INTO modules (key, name, description, is_core)
VALUES
    ('crm', 'CRM', 'Customer relationship management', TRUE),
    ('sales', 'Sales', 'Leads, deals, and pipeline management', TRUE),
    ('support', 'Support', 'Ticketing and customer support', TRUE),
    ('billing', 'Billing', 'Subscriptions, invoicing, and payments', FALSE),
    ('network', 'Network', 'RADIUS and network operations', FALSE),
    ('iot', 'IoT', 'Device telemetry and management', FALSE),
    ('retention', 'Retention', 'Churn analytics and retention', FALSE),
    ('call_center', 'Call Center', 'Agent scripts and sentiment', FALSE),
    ('analytics', 'Analytics', 'Executive summaries and insights', FALSE),
    ('inventory', 'Inventory', 'Stock and warehousing', FALSE),
    ('hr', 'HR', 'Staff and talent management', FALSE),
    ('rica', 'RICA', 'Compliance and verification', FALSE)
ON CONFLICT (key) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_core = EXCLUDED.is_core;

INSERT INTO permissions (key, description)
VALUES
    ('platform.admin', 'Full platform access'),
    ('org.manage', 'Manage organisations and org settings'),
    ('module.manage', 'Manage tenant module entitlements'),
    ('org.admin', 'Organisation administrator'),
    ('crm.read', 'Read CRM data'),
    ('crm.write', 'Write CRM data'),
    ('crm.admin', 'Administer CRM'),
    ('sales.read', 'Read sales data'),
    ('sales.write', 'Write sales data'),
    ('sales.admin', 'Administer sales'),
    ('support.read', 'Read support data'),
    ('support.write', 'Write support data'),
    ('support.admin', 'Administer support'),
    ('billing.read', 'Read billing data'),
    ('billing.write', 'Write billing data'),
    ('billing.admin', 'Administer billing'),
    ('network.read', 'Read network data'),
    ('network.write', 'Write network data'),
    ('network.admin', 'Administer network'),
    ('iot.read', 'Read IoT data'),
    ('iot.write', 'Write IoT data'),
    ('iot.admin', 'Administer IoT'),
    ('retention.read', 'Read retention data'),
    ('retention.write', 'Write retention data'),
    ('retention.admin', 'Administer retention'),
    ('call_center.read', 'Read call center data'),
    ('call_center.write', 'Write call center data'),
    ('call_center.admin', 'Administer call center'),
    ('analytics.read', 'Read analytics data'),
    ('analytics.write', 'Write analytics data'),
    ('analytics.admin', 'Administer analytics'),
    ('inventory.read', 'Read inventory data'),
    ('inventory.write', 'Write inventory data'),
    ('inventory.admin', 'Administer inventory'),
    ('hr.read', 'Read HR data'),
    ('hr.write', 'Write HR data'),
    ('hr.admin', 'Administer HR'),
    ('rica.read', 'Read RICA data'),
    ('rica.write', 'Write RICA data'),
    ('rica.admin', 'Administer RICA')
ON CONFLICT (key) DO NOTHING;

INSERT INTO roles (id, tenant_id, name, scope, description, is_system)
VALUES (uuid_generate_v4(), NULL, 'platform_admin', 'PLATFORM', 'Platform super admin', TRUE)
ON CONFLICT (name) WHERE tenant_id IS NULL DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON TRUE
WHERE r.name = 'platform_admin' AND r.tenant_id IS NULL
ON CONFLICT DO NOTHING;

-- Provision a tenant with default roles, permissions, and core modules
CREATE OR REPLACE FUNCTION provision_tenant(p_tenant_id UUID, p_admin_user_id UUID DEFAULT NULL)
RETURNS VOID AS $$
DECLARE
    v_org_admin_role UUID;
    v_org_user_role UUID;
BEGIN
    INSERT INTO roles (tenant_id, name, scope, description, is_system)
    VALUES (p_tenant_id, 'org_admin', 'TENANT', 'Organisation administrator', TRUE)
    ON CONFLICT (tenant_id, name) DO UPDATE SET description = EXCLUDED.description
    RETURNING id INTO v_org_admin_role;

    IF v_org_admin_role IS NULL THEN
        SELECT id INTO v_org_admin_role FROM roles WHERE tenant_id = p_tenant_id AND name = 'org_admin';
    END IF;

    INSERT INTO roles (tenant_id, name, scope, description, is_system)
    VALUES (p_tenant_id, 'org_user', 'TENANT', 'Organisation user', TRUE)
    ON CONFLICT (tenant_id, name) DO UPDATE SET description = EXCLUDED.description
    RETURNING id INTO v_org_user_role;

    IF v_org_user_role IS NULL THEN
        SELECT id INTO v_org_user_role FROM roles WHERE tenant_id = p_tenant_id AND name = 'org_user';
    END IF;

    INSERT INTO role_permissions (role_id, permission_id)
    SELECT v_org_admin_role, p.id
    FROM permissions p
    WHERE p.key NOT LIKE 'platform.%'
      AND p.key NOT IN ('module.manage', 'org.manage')
    ON CONFLICT DO NOTHING;

    INSERT INTO role_permissions (role_id, permission_id)
    SELECT v_org_user_role, p.id
    FROM permissions p
    WHERE p.key LIKE '%.read'
    ON CONFLICT DO NOTHING;

    INSERT INTO tenant_modules (tenant_id, module_id, status)
    SELECT p_tenant_id, m.id, 'ENABLED'
    FROM modules m
    WHERE m.is_core = TRUE
    ON CONFLICT (tenant_id, module_id) DO NOTHING;

    IF p_admin_user_id IS NOT NULL THEN
        INSERT INTO user_roles (user_id, role_id, tenant_id, assigned_by)
        VALUES (p_admin_user_id, v_org_admin_role, p_tenant_id, p_admin_user_id)
        ON CONFLICT (user_id, role_id, tenant_id) DO NOTHING;
    END IF;
END;
$$ LANGUAGE plpgsql;
