-- Demo team members (login users) for the dev tenant so the Communication
-- module shows a real multi-person conversation. Supabase auth users are created
-- separately (admin API); these are the matching backend users rows + message
-- attribution. Password for all: OmniDomeTest2026!  (via Supabase).

INSERT INTO users (id, tenant_id, email, full_name, role, hashed_password, is_active) VALUES
 ('4fcf3d12-9315-4be0-ae3d-63c95eeb9ca1','00000000-0000-0000-0000-000000000001','sarah@omnidome.local','Sarah Chen','USER','supabase-managed-no-local-login',true),
 ('3820b0bc-107e-45b4-b639-c28ed6cb0705','00000000-0000-0000-0000-000000000001','mike@omnidome.local','Mike Johnson','USER','supabase-managed-no-local-login',true),
 ('b3277740-b7ae-48e7-850c-15e73ce88555','00000000-0000-0000-0000-000000000001','emily@omnidome.local','Emily Davis','USER','supabase-managed-no-local-login',true)
ON CONFLICT (id) DO NOTHING;

-- Attribute the seeded channel messages to the demo members (multi-author view).
UPDATE messages SET user_id='4fcf3d12-9315-4be0-ae3d-63c95eeb9ca1' WHERE id='22222222-2222-2222-2222-222222222201';
UPDATE messages SET user_id='3820b0bc-107e-45b4-b639-c28ed6cb0705' WHERE id='22222222-2222-2222-2222-222222222202';
UPDATE messages SET user_id='b3277740-b7ae-48e7-850c-15e73ce88555' WHERE id='22222222-2222-2222-2222-222222222203';
