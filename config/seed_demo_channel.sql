-- Demo channel + messages for the dev tenant so the Communication module shows
-- real (DB-backed) team chat and right-click actions can target a real channel.
-- Idempotent. created_by/user_id = the seeded test user (test@omnidome.local).

INSERT INTO channels (id, tenant_id, name, description, is_private, created_by)
VALUES ('11111111-1111-1111-1111-111111111111',
        '00000000-0000-0000-0000-000000000001',
        'sales-team', 'Sales team channel', false,
        '687fc528-cee6-4021-9e29-28344b3d6d0d')
ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, channel_id, tenant_id, user_id, content, is_pinned) VALUES
 ('22222222-2222-2222-2222-222222222201',
  '11111111-1111-1111-1111-111111111111', '00000000-0000-0000-0000-000000000001',
  '687fc528-cee6-4021-9e29-28344b3d6d0d',
  'Hey team! Just closed the Meridian account - R450K MRR!', true),
 ('22222222-2222-2222-2222-222222222202',
  '11111111-1111-1111-1111-111111111111', '00000000-0000-0000-0000-000000000001',
  '687fc528-cee6-4021-9e29-28344b3d6d0d',
  'Amazing work! That''s our biggest deal this quarter.', false),
 ('22222222-2222-2222-2222-222222222203',
  '11111111-1111-1111-1111-111111111111', '00000000-0000-0000-0000-000000000001',
  '687fc528-cee6-4021-9e29-28344b3d6d0d',
  'Reminder: Q4 pipeline reviews are due by end of day Friday.', false)
ON CONFLICT (id) DO NOTHING;
