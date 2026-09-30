# User onboarding (tenant + roles)

`apps/web/proxy.ts` trusts only the verified Supabase user:

- Tenant: backend `users` table (admin service, by email) else `app_metadata.tenant_id`.
- Roles: only `app_metadata.roles`. None means `org_user`, read-only.
- No tenant means HTTP 403 `tenant_unresolved`. This is what a brand-new signup gets.

`app_metadata` is writable only with the service-role key, so users cannot grant
themselves anything. Use `scripts/manage_users.py` (reads `.env`, never prints keys):

```
python scripts/manage_users.py list
python scripts/manage_users.py set-tenant person@example.com <tenant_uuid>
python scripts/manage_users.py set-roles  person@example.com org_admin
python scripts/manage_users.py set-roles  person@example.com hr_manager,manager
python scripts/manage_users.py link-employees            # dry run
python scripts/manage_users.py link-employees --apply    # sets employees.user_id
```

Steps for a new person:
1. They sign up (Supabase). Until step 2 they get 403 `tenant_unresolved`.
2. The owner runs `set-tenant`, then `set-roles`. Unknown roles are refused.
   `platform_admin` needs `--i-know`. The user must sign in again for a new token.
3. Make sure an `employees` row exists with the same email (case-insensitive),
   then run `link-employees --apply`. This is what makes KPI self-approval blocking work.

If the service-role key is rejected (401/403) the script prints the SQL to run in the
Supabase SQL editor instead. Regenerate the key in the dashboard (Settings > API) and update `.env`.

Roles services check today: `org_admin`, `org_user` (tenant defaults from `provision_tenant`),
`hr_manager`/`hr`/`hr_admin` (HR admin: KPI approve, reject, reopen), `manager`/`line_manager`
(KPI approve/reject), `admin`/`owner`/`tenant_admin`/`super_admin` (HR and marketing admin gates),
`platform_admin` (cross-tenant).

Caveats:
- HR does not treat `org_admin` as an HR admin. Give HR staff `hr_manager`.
- `link-employees` uses the backend `users.id` when the email exists there, otherwise the Supabase id,
  the same order the proxy uses.
- The admin service has `/users`, `/roles` and `/users/{id}/roles` for DB-backed RBAC (needs tenant admin).
  Those are separate from the Supabase `app_metadata.roles` that proxy.ts reads. Roles in the backend
  `roles` table for a tenant only exist after `provision_tenant()` has been run.
