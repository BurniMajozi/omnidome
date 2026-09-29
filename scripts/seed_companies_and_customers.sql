-- Connect B2B leads to companies and converted leads to customers
BEGIN;

DO $$
DECLARE
    v_tenant_id uuid := '00000000-0000-0000-0000-000000000001';
    v_comp_seapoint uuid := uuid_generate_v4();
    v_comp_worksmarket uuid := uuid_generate_v4();
    v_comp_worksmain uuid := uuid_generate_v4();
    v_comp_sita uuid := uuid_generate_v4();
    v_comp_apex uuid := uuid_generate_v4();
    v_comp_metro uuid := uuid_generate_v4();
    v_comp_afrihost uuid := uuid_generate_v4();

    v_cust_zanele uuid := uuid_generate_v4();
    v_cust_marco uuid := uuid_generate_v4();
    v_cust_priya uuid := uuid_generate_v4();
    v_cust_lerato uuid := uuid_generate_v4();
    v_cust_david uuid := uuid_generate_v4();
    v_cust_refiloe uuid := uuid_generate_v4();
    v_cust_tobias uuid := uuid_generate_v4();
    v_cust_naledi uuid := uuid_generate_v4();
    v_cust_farai uuid := uuid_generate_v4();
    v_cust_kgosi uuid := uuid_generate_v4();
    v_cust_bradley uuid := uuid_generate_v4();
BEGIN
    -- 1. Insert Companies from B2B Leads if they don't exist
    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Sea Point Holiday Hotel') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_seapoint, v_tenant_id, 'Sea Point Holiday Hotel', '2021/045892/07', 'Hospitality & Tourism',
            'Farai Dube', 'reservations@seapoint.co.za', '+27 21 439 4433', 'Main Road, Cape Town Ward 54, Cape Town',
            'Net 30', 50000.00, true, 'Converted from OpenStreetMap hospitality lead search. 1 Gbps Dedicated Fibre.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_seapoint FROM companies WHERE name = 'Sea Point Holiday Hotel' LIMIT 1;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Works@Market Industrial') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_worksmarket, v_tenant_id, 'Works@Market Industrial', '2019/382910/07', 'Manufacturing & Industrial',
            'Bradley Smith', 'ops@worksmarket.co.za', '011 378 3200', 'Von Brandis Street, Marshalltown, Johannesburg',
            'Net 30', 75000.00, true, 'Industrial & manufacturing park. High-capacity redundant link.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_worksmarket FROM companies WHERE name = 'Works@Market Industrial' LIMIT 1;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Works@Main Logistics Hub') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_worksmain, v_tenant_id, 'Works@Main Logistics Hub', '2020/559281/07', 'Logistics & Supply Chain',
            'Siphesihle Zuma', 'logistics@worksmain.co.za', '011 378 5500', 'Main Street, Marshalltown, Johannesburg',
            'Net 30', 45000.00, true, 'Freight logistics coordination node. Business 500 Mbps Fibre.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_worksmain FROM companies WHERE name = 'Works@Main Logistics Hub' LIMIT 1;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'SITA Public Sector Systems') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_sita, v_tenant_id, 'SITA Public Sector Systems', '1998/018991/30', 'Government & Public Sector',
            'Kgosi Maluleke', 'tenders@sita.co.za', '012 482 3000', '459 Tsitsa Street, Erasmuskloof, Pretoria',
            'Net 60', 250000.00, true, 'State Information Technology Agency (RFB 3276_2026 tender). Tier-1 SLA.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_sita FROM companies WHERE name = 'SITA Public Sector Systems' LIMIT 1;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Apex Engineering Cape') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_apex, v_tenant_id, 'Apex Engineering Cape', '2018/491029/07', 'Engineering & Construction',
            'David Thompson', 'david.t@apexeng.co.za', '021 888 1200', '37 Church St, Stellenbosch',
            'Net 30', 60000.00, true, 'Engineering consultancy with 4 branch offices in Western Cape.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_apex FROM companies WHERE name = 'Apex Engineering Cape' LIMIT 1;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Metropolitan Freight Solutions') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_metro, v_tenant_id, 'Metropolitan Freight Solutions', '2022/718290/07', 'Transport & Marine',
            'Priya Naidoo', 'priya.n@metrofreight.co.za', '031 361 8000', '170 Long St, Durban',
            'Net 30', 80000.00, true, 'Port of Durban marine logistics tracking and telemetry communications.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_metro FROM companies WHERE name = 'Metropolitan Freight Solutions' LIMIT 1;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM companies WHERE name = 'Afrihost Business Park Node') THEN
        INSERT INTO companies (
            id, tenant_id, name, registration_number, industry, contact_person,
            email, phone, address, payment_terms, credit_limit_zar, is_active, notes, created_at, updated_at
        ) VALUES (
            v_comp_afrihost, v_tenant_id, 'Afrihost Business Park Node', '2017/639102/07', 'Telecommunications',
            'Refiloe Mofokeng', 'admin@afrihostpark.co.za', '011 612 7000', '144 Park Ave, Midrand',
            'Net 30', 120000.00, true, 'Commercial business park aggregation node. Dual fiber uplinks.',
            now(), now()
        );
    ELSE
        SELECT id INTO v_comp_afrihost FROM companies WHERE name = 'Afrihost Business Park Node' LIMIT 1;
    END IF;

    -- 2. Insert Converted Leads into Customers (People)
    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'zanele.m@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_zanele, v_tenant_id, 'Zanele', 'Mkhize', 'zanele.m@email.co.za', '0836667788', '8904125029087',
            '120 Ridge Rd, Paarl', 'western_cape', 'ACC-2026-09281A', 'active', true, NULL, NULL,
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'marco.f@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_marco, v_tenant_id, 'Marco', 'Ferreira', 'marco.f@email.co.za', '0728889900', '8507235081084',
            '118 Ridge Rd, Pietermaritzburg', 'kwazulu_natal', 'ACC-2026-09282B', 'active', true, NULL, NULL,
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'priya.n@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_priya, v_tenant_id, 'Priya', 'Naidoo', 'priya.n@email.co.za', '0841110022', '9211055019082',
            '170 Long St, Pietermaritzburg', 'kwazulu_natal', 'ACC-2026-09283C', 'active', true, v_comp_metro, 'Operations Director',
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'lerato@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_lerato, v_tenant_id, 'Lerato', 'Khumalo', 'lerato@email.co.za', '0821234567', '9402155092083',
            '112 Park Ave, Tzaneen', 'limpopo', 'ACC-2026-09284D', 'active', true, NULL, NULL,
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'david.t@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_david, v_tenant_id, 'David', 'Thompson', 'david.t@email.co.za', '0765554433', '8106195044081',
            '37 Church St, Stellenbosch', 'western_cape', 'ACC-2026-09285E', 'active', true, v_comp_apex, 'Managing Director',
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'refiloe.m@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_refiloe, v_tenant_id, 'Refiloe', 'Mofokeng', 'refiloe.m@email.co.za', '0832221100', '9008225031089',
            '100 Market St, Sandton', 'gauteng', 'ACC-2026-09286F', 'active', true, v_comp_afrihost, 'Network Administrator',
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'tobias.vw@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_tobias, v_tenant_id, 'Tobias', 'van Wyk', 'tobias.vw@email.co.za', '0733334455', '8703115062085',
            '138 Church St, Pietermaritzburg', 'kwazulu_natal', 'ACC-2026-09287G', 'active', true, NULL, NULL,
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'naledi.p@email.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_naledi, v_tenant_id, 'Naledi', 'Pillay', 'naledi.p@email.co.za', '0829991122', '9312105077080',
            '62 Church St, Bloemfontein', 'free_state', 'ACC-2026-09288H', 'active', true, NULL, NULL,
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'farai.dube@seapoint.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_farai, v_tenant_id, 'Farai', 'Dube', 'farai.dube@seapoint.co.za', '+27 21 439 4433', '8605145028086',
            'Main Road, Cape Town Ward 54, Cape Town', 'western_cape', 'ACC-2026-09289J', 'active', true, v_comp_seapoint, 'General Manager',
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'kgosi@sita.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_kgosi, v_tenant_id, 'Kgosi', 'Maluleke', 'kgosi@sita.co.za', '012 482 3000', '7909285094082',
            '459 Tsitsa Street, Erasmuskloof, Pretoria', 'gauteng', 'ACC-2026-09290K', 'active', true, v_comp_sita, 'Procurement Director',
            now(), now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM customers WHERE email = 'bradley@worksmarket.co.za') THEN
        INSERT INTO customers (
            id, tenant_id, first_name, last_name, email, phone, id_number,
            address, province, account_number, status, rica_verified, company_id, company_role,
            created_at, updated_at
        ) VALUES (
            v_cust_bradley, v_tenant_id, 'Bradley', 'Smith', 'bradley@worksmarket.co.za', '011 378 3200', '8408175053088',
            'Von Brandis Street, Marshalltown, Johannesburg', 'gauteng', 'ACC-2026-09291L', 'active', true, v_comp_worksmarket, 'Plant Director',
            now(), now()
        );
    END IF;

    -- 3. Link leads.converted_customer_id to the created customer records
    UPDATE leads SET converted_customer_id = (SELECT id FROM customers WHERE email = 'zanele.m@email.co.za' LIMIT 1) WHERE email = 'zanele.m@email.co.za';
    UPDATE leads SET converted_customer_id = (SELECT id FROM customers WHERE email = 'marco.f@email.co.za' LIMIT 1) WHERE email = 'marco.f@email.co.za';
    UPDATE leads SET converted_customer_id = (SELECT id FROM customers WHERE email = 'priya.n@email.co.za' LIMIT 1) WHERE email = 'priya.n@email.co.za';
    UPDATE leads SET converted_customer_id = (SELECT id FROM customers WHERE email = 'farai.dube@seapoint.co.za' LIMIT 1) WHERE first_name ILIKE '%Sea Point%';
    UPDATE leads SET converted_customer_id = (SELECT id FROM customers WHERE email = 'bradley@worksmarket.co.za' LIMIT 1) WHERE first_name ILIKE '%Works@Market%';
    UPDATE leads SET converted_customer_id = (SELECT id FROM customers WHERE email = 'kgosi@sita.co.za' LIMIT 1) WHERE first_name ILIKE '%SITA%';

END $$;

COMMIT;
