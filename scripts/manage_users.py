#!/usr/bin/env python3
"""Manage OmniDome auth users: roles, tenant, and HR employee linking.

Subcommands
  list                               Supabase users + app_metadata roles/tenant
  set-roles  <email> <r1,r2,...>     write app_metadata.roles   (Auth Admin API)
  set-tenant <email> <tenant_uuid>   write app_metadata.tenant_id
  link-employees [--apply]           set hr.employees.user_id where email matches
                                     an auth user exactly (case-insensitive);
                                     dry-run unless --apply

Config (env or repo-root .env; keys are never printed):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  POSTGRES_USER / POSTGRES_DB       (default admin / coreconnect)
  OMNIDOME_PSQL                     command that reads SQL on stdin, e.g.
                                    "docker exec -i omnidome-db-1 psql -U admin -d coreconnect"
                                    (default: that, wrapped in wsl.exe on Windows)

If the service-role key is rejected (401/403) the script prints the exact SQL to
run in the Supabase SQL editor instead. Roles/tenant live in app_metadata, which
only the service role can write; proxy.ts reads them from the verified user.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Roles that some service actually checks (see docs/user-onboarding.md).
KNOWN_ROLES = {
    "org_admin", "org_user",                          # provision_tenant() defaults; admin service
    "hr_manager", "hr", "hr_admin",                   # HR: KPI approve/reopen (services/hr/main.py)
    "manager", "line_manager",                        # HR: KPI approve/reject
    "admin", "owner", "tenant_admin", "super_admin",  # HR/marketing admin gates
    "platform_admin",                                 # cross-tenant; needs --i-know
}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env = dict(os.environ)
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


ENV = load_env()


class AuthRejected(Exception):
    pass


def supa(method, path, body=None):
    url, key = ENV.get("SUPABASE_URL", ""), ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise AuthRejected("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    req = urllib.request.Request(
        url.rstrip("/") + "/auth/v1/admin" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthRejected(f"Supabase rejected the service-role key (HTTP {e.code}). "
                               "Regenerate it in the Supabase dashboard (Settings > API) and update .env.")
        raise SystemExit(f"Supabase error HTTP {e.code}")


def all_users():
    users, page = [], 1
    while True:
        data = supa("GET", f"/users?page={page}&per_page=200")
        batch = data.get("users", [])
        users += batch
        if len(batch) < 200:
            return users
        page += 1


def find_user(email):
    for u in all_users():
        if (u.get("email") or "").lower() == email.lower():
            return u
    raise SystemExit(f"No auth user with email {email}")


def sql_fallback(email, patch):
    print("\n-- Run in the Supabase SQL editor:")
    print("update auth.users set raw_app_meta_data = raw_app_meta_data || "
          f"'{json.dumps(patch)}'::jsonb where lower(email) = lower('{email.replace(chr(39), chr(39)*2)}');")


def update_app_meta(email, patch):
    try:
        u = find_user(email)
        supa("PUT", f"/users/{u['id']}", {"app_metadata": patch})
        print(f"[applied] {email}: app_metadata += {json.dumps(patch)}")
    except AuthRejected as e:
        print(f"[not applied] {e}")
        sql_fallback(email, patch)
        return 2
    return 0


def psql(sql):
    cmd = ENV.get("OMNIDOME_PSQL")
    if not cmd:
        u, d = ENV.get("POSTGRES_USER", "admin"), ENV.get("POSTGRES_DB", "coreconnect")
        cmd = f"docker exec -i omnidome-db-1 psql -U {u} -d {d}"
        if os.name == "nt":
            cmd = "wsl.exe -d Ubuntu-26.04 -- " + cmd
    r = subprocess.run(cmd + " --csv -t", shell=True,
                       input=sql, capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise SystemExit("psql failed: " + r.stderr.strip()[:300])
    return [row for row in csv.reader(r.stdout.splitlines()) if row]


def q(s):
    return "'" + s.replace("'", "''") + "'"


def cmd_list(_a):
    try:
        for u in all_users():
            am = u.get("app_metadata") or {}
            print(f"{u['email']:40} tenant={am.get('tenant_id', '-')} roles={','.join(am.get('roles', [])) or '-'}")
    except AuthRejected as e:
        print(e)
        return 2


AUTHORITY_WARNING = chr(10).join([
    "WARNING: the admin service DB is authoritative for tenant/roles/seats; Supabase app_metadata is a",
    "derived cache. This break-glass write BYPASSES seat limits, rank guardrails and the audit log, and",
    "the next admin-service sync (or POST /admin/sync/reconcile?apply=true) will overwrite it. Prefer the",
    "admin API (POST /tenants/{id}/invites, PUT /tenants/{id}/members/{uid}/roles).",
])


def cmd_set_roles(a):
    print(AUTHORITY_WARNING, file=sys.stderr)
    roles = [r.strip() for r in a.roles.split(",") if r.strip()]
    bad = [r for r in roles if r not in KNOWN_ROLES]
    if bad:
        raise SystemExit(f"Unknown role(s) {bad}. Known: {sorted(KNOWN_ROLES)}")
    if "platform_admin" in roles and not a.i_know:
        raise SystemExit("platform_admin is cross-tenant; pass --i-know to grant it")
    return update_app_meta(a.email, {"roles": roles})


def cmd_set_tenant(a):
    print(AUTHORITY_WARNING, file=sys.stderr)
    if not UUID_RE.match(a.tenant):
        raise SystemExit("tenant must be a UUID")
    return update_app_meta(a.email, {"tenant_id": a.tenant})


def cmd_link(a):
    try:
        users = all_users()
    except AuthRejected as e:
        print(e)
        return 2
    by_email = {(u.get("email") or "").lower(): u for u in users}
    # The proxy prefers the backend users.id (admin service) over the Supabase id.
    backend = {r[0].lower(): r[1] for r in psql("select email, id from users;")}
    emps = psql("select id, lower(email), tenant_id, coalesce(user_id::text,'') from employees "
                "where email is not null;")
    n = 0
    for eid, email, etenant, cur in emps:
        u = by_email.get(email)
        if not u:
            continue
        atenant = (u.get("app_metadata") or {}).get("tenant_id")
        if atenant and atenant.lower() != etenant.lower():
            print(f"[skip] {email}: tenant mismatch")
            continue
        uid = backend.get(email) or u["id"]
        if cur.lower() == uid.lower():
            continue
        print(f"[{'link' if a.apply else 'dry-run'}] employee {eid} {email} -> user_id {uid}")
        if a.apply:
            psql(f"update employees set user_id = {q(uid)}::uuid where id = {q(eid)}::uuid;")
        n += 1
    print(f"{n} employee(s) {'linked' if a.apply else 'would be linked (use --apply)'}; "
          f"{len(emps)} employees with email checked")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="c", required=True)
    s.add_parser("list").set_defaults(f=cmd_list)
    x = s.add_parser("set-roles")
    x.add_argument("email"); x.add_argument("roles"); x.add_argument("--i-know", action="store_true")
    x.set_defaults(f=cmd_set_roles)
    x = s.add_parser("set-tenant")
    x.add_argument("email"); x.add_argument("tenant")
    x.set_defaults(f=cmd_set_tenant)
    x = s.add_parser("link-employees")
    x.add_argument("--apply", action="store_true")
    x.set_defaults(f=cmd_link)
    a = p.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
