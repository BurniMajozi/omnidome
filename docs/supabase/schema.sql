-- Core schema for chat/task/approval/schedule flows
-- Run in Supabase SQL editor.

create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text unique,
  avatar text,
  status text default 'offline',
  created_at timestamptz default now()
);

create table if not exists teams (
  id uuid primary key default gen_random_uuid(),
  name text not null
);

create table if not exists memberships (
  user_id uuid references users(id) on delete cascade,
  team_id uuid references teams(id) on delete cascade,
  role text not null,
  primary key (user_id, team_id)
);

create table if not exists channels (
  id uuid primary key default gen_random_uuid(),
  team_id uuid references teams(id) on delete cascade,
  name text not null,
  is_private boolean default false,
  created_at timestamptz default now()
);

create table if not exists channel_members (
  channel_id uuid references channels(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  primary key (channel_id, user_id)
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  channel_id uuid references channels(id) on delete cascade,
  user_id uuid references users(id) on delete set null,
  author_name text,
  author_avatar text,
  content text not null,
  created_at timestamptz default now(),
  thread_root_id uuid references messages(id) on delete set null,
  is_pinned boolean default false
);

alter table if exists messages
  add column if not exists author_name text,
  add column if not exists author_avatar text;

create table if not exists message_reactions (
  id uuid primary key default gen_random_uuid(),
  message_id uuid references messages(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  emoji text not null,
  created_at timestamptz default now()
);

create table if not exists message_reads (
  message_id uuid references messages(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  read_at timestamptz default now(),
  primary key (message_id, user_id)
);

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  channel_id uuid references channels(id) on delete set null,
  title text not null,
  description text,
  status text default 'todo',
  priority text default 'medium',
  due_at timestamptz,
  due_date_label text,
  notes text,
  created_at timestamptz default now(),
  created_by uuid references users(id) on delete set null,
  assigned_to uuid references users(id) on delete set null,
  source_message_id uuid references messages(id) on delete set null
);

create table if not exists approvals (
  id uuid primary key default gen_random_uuid(),
  subject text,
  type text not null,
  amount text,
  reason text,
  status text default 'pending',
  timeline text,
  notes text,
  requested_by uuid references users(id) on delete set null,
  approver_id uuid references users(id) on delete set null,
  source_message_id uuid references messages(id) on delete set null,
  created_at timestamptz default now(),
  decided_at timestamptz
);

create table if not exists schedule_events (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  type text not null,
  start_at timestamptz not null,
  end_at timestamptz,
  date_label text,
  time_label text,
  notes text,
  source_message_id uuid references messages(id) on delete set null,
  owner_id uuid references users(id) on delete set null,
  linked_task_id uuid references tasks(id) on delete set null,
  status text default 'upcoming',
  created_at timestamptz default now()
);

create table if not exists leads (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  company text,
  value text,
  status text default 'new',
  owner_id uuid references users(id) on delete set null,
  source_message_id uuid references messages(id) on delete set null,
  created_at timestamptz default now()
);

create table if not exists escalations (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  customer text,
  severity text not null,
  status text default 'open',
  notes text,
  owner_id uuid references users(id) on delete set null,
  source_message_id uuid references messages(id) on delete set null,
  created_at timestamptz default now()
);

alter table if exists tasks
  add column if not exists due_date_label text,
  add column if not exists notes text;

alter table if exists approvals
  add column if not exists subject text,
  add column if not exists timeline text,
  add column if not exists notes text;

alter table if exists schedule_events
  add column if not exists date_label text,
  add column if not exists time_label text,
  add column if not exists notes text,
  add column if not exists source_message_id uuid references messages(id) on delete set null;

alter table if exists escalations
  add column if not exists notes text;

create table if not exists email_threads (
  id uuid primary key default gen_random_uuid(),
  external_id text,
  subject text,
  customer_id text,
  created_at timestamptz default now()
);

create table if not exists email_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid references email_threads(id) on delete set null,
  direction text not null,
  sender text,
  recipients text,
  subject text,
  body text,
  sent_at timestamptz,
  linked_task_id uuid references tasks(id) on delete set null,
  linked_approval_id uuid references approvals(id) on delete set null
);

create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  payload jsonb not null,
  created_at timestamptz default now()
);

-- Generic module data storage for dashboard modules
create table if not exists module_data (
  module_id text primary key,
  data jsonb not null,
  updated_at timestamptz default now()
);

alter table module_data enable row level security;

drop policy if exists module_data_read on module_data;
create policy module_data_read on module_data
  for select
  to anon, authenticated
  using (true);

grant select on table module_data to anon, authenticated;

create or replace function touch_module_data_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists module_data_updated_at on module_data;
create trigger module_data_updated_at
before update on module_data
for each row execute function touch_module_data_updated_at();
