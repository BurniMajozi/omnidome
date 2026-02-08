-- Seed initial platform admin user and role assignment.
-- Update the UUID/email/password before running in production.

DO $$
DECLARE
    v_user_id UUID := '11111111-1111-1111-1111-111111111111';
    v_email TEXT := 'platform.admin@coreconnect.local';
    v_full_name TEXT := 'Platform Admin';
    v_password TEXT := 'CHANGE_ME_HASHED_PASSWORD';
    v_role_id UUID;
BEGIN
    INSERT INTO users (id, tenant_id, email, full_name, role, hashed_password, is_active)
    VALUES (v_user_id, NULL, v_email, v_full_name, 'ADMIN', v_password, TRUE)
    ON CONFLICT (email) DO UPDATE
        SET full_name = EXCLUDED.full_name,
            is_active = TRUE
    RETURNING id INTO v_user_id;

    SELECT id INTO v_role_id
    FROM roles
    WHERE name = 'platform_admin' AND tenant_id IS NULL;

    IF v_role_id IS NULL THEN
        INSERT INTO roles (id, tenant_id, name, scope, description, is_system)
        VALUES (uuid_generate_v4(), NULL, 'platform_admin', 'PLATFORM', 'Platform super admin', TRUE)
        RETURNING id INTO v_role_id;

        INSERT INTO role_permissions (role_id, permission_id)
        SELECT v_role_id, id
        FROM permissions
        ON CONFLICT DO NOTHING;
    END IF;

    INSERT INTO user_roles (user_id, role_id, tenant_id, assigned_by)
    VALUES (v_user_id, v_role_id, NULL, v_user_id)
    ON CONFLICT DO NOTHING;
END $$;

-- Quick sanity check
SELECT u.id, u.email, r.name AS role
FROM users u
JOIN user_roles ur ON ur.user_id = u.id
JOIN roles r ON r.id = ur.role_id
WHERE u.email = 'platform.admin@coreconnect.local';
