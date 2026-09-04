# scripts/railway — phase-1 deploy automation

Automates the repetitive parts of the Railway migration described in
[`docs/railway-migration.md`](../../docs/railway-migration.md). It creates the
core-subset services, sets each service's variables, generates public domains,
and wires the domain-dependent variables — reading secrets from the repo-root
`.env` at runtime so **no secret is ever committed**.

## Layout
```
scripts/railway/
  deploy.sh         # the helper (bash; run under Git Bash on Windows)
  env/
    _shared.env     # vars applied to every Python backend service
    <service>.env   # per-service vars (RAILWAY_DOCKERFILE_PATH + extras)
    web.env         # Next.js app: internal *.railway.internal URLs + Supabase
    hermes.env      # cloud Hermes agent (OpenRouter)
```

### Sentinels used in the env files
| Token | Resolved to |
|---|---|
| `@from-dotenv:KEY` | value of `KEY` from repo-root `.env` (secrets) |
| `${{Postgres.DATABASE_URL}}` | Railway reference variable (set literally) |
| `@gateway-domain` | gateway's public HTTPS URL (filled in `wire`) |
| `@web-domain` | web's public HTTPS URL (filled in `wire`) |

## One-time prerequisites (not scriptable)
1. `railway login`
2. Authorize the **Railway GitHub app** for `BurniMajozi/omnidome` (so
   `railway add --repo` can build from the repo). Dashboard → project → GitHub.
3. From the repo root: `railway init` (creates the project), then `railway link`
   in any new shell.

## Run it
```bash
scripts/railway/deploy.sh preflight   # verify login + linked project + .env
scripts/railway/deploy.sh db          # provision Postgres, then load master_schema.sql (prints the psql cmd)
scripts/railway/deploy.sh create      # create all 13 services + set their vars
scripts/railway/deploy.sh domains     # generate public domains for gateway + web
scripts/railway/deploy.sh wire        # set NEXT_PUBLIC_GATEWAY_URL + CORS_ORIGINS, redeploy
# or the whole thing:
scripts/railway/deploy.sh all
# single service (create, or re-apply its vars if it already exists):
scripts/railway/deploy.sh create crm
```

After `db`, actually load the schema (once):
```bash
railway run -- psql "$DATABASE_URL" -f config/master_schema.sql
```

## Notes / gotchas
- **Dockerfile per service** is selected by the `RAILWAY_DOCKERFILE_PATH` variable
  (in each `env/*.env`) — no dashboard build config needed. Build context is the
  repo root, which is what the Dockerfiles expect (`COPY services/...`).
- **Private networking:** a project created now is dual-stack, so the services'
  existing `--host 0.0.0.0` binds are reachable over `*.railway.internal`. If you
  ever see internal calls hang (legacy IPv6-only env), set a **custom start
  command** per Python service binding `::`, e.g. gateway:
  `uvicorn services.gateway.main:app --host :: --port 8000 --workers 2`
- **Licenses:** phase 1 runs with `LICENSE_ENFORCEMENT=false` (no bind mounts on
  Railway). To enforce later, bake `licenses/license.json` into each image.
- **gateway public port:** gateway listens on 8000; if the generated domain 502s,
  set the service's public target port to 8000 (Networking tab).
- **Hermes** needs a **Railway Volume mounted at `/opt/data`** (add it in the
  dashboard after `create hermes`), and — if you want repo access — set
  `OMNIDOME_REPO_URL` in `env/hermes.env` to an HTTPS URL that includes a GitHub
  token. See `services/hermes/` and `docs/railway-migration.md`.
- The script sets vars with `--skip-deploys` during `create` to avoid thrashing;
  `wire` sets without it so the dependent services redeploy once.
- Re-runnable: if a service already exists, `create` falls back to re-applying its
  variables instead of failing.
