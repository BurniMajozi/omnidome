ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS owner_department varchar(100) NOT NULL DEFAULT 'HR';
ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'TODO';
ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS sort_order int NOT NULL DEFAULT 0;
ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
