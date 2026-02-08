-- Optional retention helpers for demo environments.
-- Run manually or schedule with pg_cron if available.

create or replace function cleanup_demo_data() returns void as $$
begin
  delete from message_reactions where created_at < now() - interval '30 days';
  delete from message_reads where read_at < now() - interval '30 days';
  delete from messages where created_at < now() - interval '30 days';
  delete from events where created_at < now() - interval '30 days';
end;
$$ language plpgsql;

-- If pg_cron is enabled, schedule a daily cleanup at 03:00.
-- create extension if not exists pg_cron;
-- select cron.schedule('cleanup-demo-data', '0 3 * * *', $$ call cleanup_demo_data(); $$);
