# OmniDome → Railway migration

Goal: get the OmniDome stack (and Hermes) off local Docker — which is heavy /
unstable on this machine (WSL crashes, HDD storage, no GPU) — and onto Railway,
**cost-controlled**, starting with a working core subset and adding the rest later.

Status: **planning / phase 1 not yet deployed.** This doc is the runbook.

---

## Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Scope | **Core subset first** | Prove the pipeline to a live URL, control the monthly bill, then fan out. |
| Database | **Railway Postgres** | True lift-and-shift of the current self-hosted `db`; same private network as services (low latency, no egress); avoids Supabase pooler connection limits with many services; keeps blast radius separate from the Supabase project that runs web auth. |
| Hermes | **Cloud agent on OpenRouter** | No GPU here; `OPENROUTER_API_KEY` already in `.env`; drops Ollama entirely → faster + cheaper. Runs standalone with its own git clone of the repo on a Railway volume. |

Supabase keeps doing exactly what it does today (web auth). We can consolidate the
microservice DB into Supabase later if ever desired; starting split de-risks the move.

---

## Core subset (phase 1)

This is **not arbitrary** — it's what `web` declares in its `depends_on`, plus `admin`
(the gateway needs it) and the DB.

| Railway service | Source Dockerfile | Internal port | Public? |
|---|---|---|---|
| Postgres | (Railway managed plugin) | 5432 | no |
| `gateway` | `services/gateway/Dockerfile` | 8000 | **yes** |
| `web` | `apps/web/Dockerfile` | 3000 | **yes** |
| `admin` | `services/admin/Dockerfile` | 8013 | no |
| `agent-orchestrator` | `services/agent_orchestrator/Dockerfile` | 8021 | no |
| `crm` | `services/crm/Dockerfile` | 8001 | no |
| `sales` | `services/sales/Dockerfile` | 8002 | no |
| `billing` | `services/billing/Dockerfile` | 8003 | no |
| `finance` | `services/finance/Dockerfile` | 8015 | no |
| `rica` | `services/rica/Dockerfile` | 8004 | no |
| `network` | `services/network/Dockerfile` | 8005 | no |
| `compliance` | `services/compliance/Dockerfile` | 8019 | no |
| `tenant-memory` | `services/tenant_memory/Dockerfile` | 8025 | no |
| `hermes` | `services/hermes/Dockerfile` (new) | 8080 (API) | optional |

Deferred to phase 2+ (features that will `503` cleanly until added): iot, call_center,
support, hr, inventory, communication, voicebox, marketing, retention, portal-builder,
journey_engine, web_analytics, lifecycle, customer_journey, billing_collections,
fno_intelligence, portal (static nginx), eCommerce/Medusa (has its own plan in
`eCommerce/docs/railway-readiness.md`).

---

## Railway gotchas that WILL bite (handle up front)

1. **Private networking + bind host.** Railway's internal DNS is
   `<service-name>.railway.internal`. A service is only reachable internally if it
   listens on IPv6 (`::`). Our services bind `0.0.0.0` (uvicorn `--host 0.0.0.0`,
   and `services/gateway/main.py` hardcodes `uvicorn.run(host="0.0.0.0", port=8000)`).
   **Fix:** set a Railway *Custom Start Command* per Python service that binds `::`,
   e.g. for gateway:
   `uvicorn services.gateway.main:app --host :: --port 8000 --workers 2`
   (Linux dual-stack serves IPv4 too.) The Dockerfile CMD is overridden by this.

2. **PORT for public services.**
   - `web` runs `next start`, which respects the `PORT` env Railway injects — leave it.
   - `gateway` is fixed to `8000`; in the Railway service's *Networking → Public
     Networking* set the target port to **8000**.

3. **No bind mounts.** Two files are bind-mounted locally:
   - `licenses/license.json` → `/etc/coreconnect/license.json`. On Railway there are
     no bind mounts. For phase 1 set **`LICENSE_ENFORCEMENT=false`** on every service
     (staging posture). To enforce later, bake the file into each image (add a
     `COPY licenses/license.json /etc/coreconnect/license.json` line) — it's 399 bytes.
   - `config/master_schema.sql` → auto-loaded by the local postgres entrypoint. On
     Railway, load it **once** after the DB exists (see step 4 below).

4. **Build context.** Every Railway service uses **Root Directory = `/`** (repo root,
   because the Dockerfiles do `COPY services/...` from root) and **Dockerfile Path =
   `services/<x>/Dockerfile`**. Set both in each service's *Settings → Build*.

5. **DATABASE_URL** is a Railway reference variable: `${{Postgres.DATABASE_URL}}`.

---

## Environment variables

### Shared across the Python services
Create a Railway **shared variable group** and attach to every Python service:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
LICENSE_ENFORCEMENT=false
INTERNAL_SERVICE_KEY=<copy from .env>
CORS_ORIGINS=https://<web-public-domain>
```

### Service-specific
| Service | Extra vars |
|---|---|
| `gateway` | `ADMIN_SERVICE_URL=http://admin.railway.internal:8013` |
| `billing` | `PAYSTACK_SECRET_KEY=<from .env>` |
| `rica` | `SMILE_ID_PARTNER_ID`, `SMILE_ID_API_KEY` (from .env) |
| `agent-orchestrator` | `OPENROUTER_API_KEY=<from .env>`, `AGENT_ORCHESTRATOR_ENABLE_TELEGRAM=false` |
| `network` | leave VUMATEL/OPENSERVE unset → mocks are skipped (external URLs optional) |

### `web` (the important one — internal URLs must point at `.railway.internal`)
```
NEXT_PUBLIC_GATEWAY_URL=https://<gateway-public-domain>
INTERNAL_SERVICE_KEY=<from .env>
ADMIN_SERVICE_URL=http://admin.railway.internal:8013
ORCHESTRATOR_URL=http://agent-orchestrator.railway.internal:8021
COMPLIANCE_SERVICE_URL=http://compliance.railway.internal:8019
TENANT_MEMORY_SERVICE_URL=http://tenant-memory.railway.internal:8025
SALES_SERVICE_URL=http://sales.railway.internal:8002
RICA_SERVICE_URL=http://rica.railway.internal:8004
NETWORK_SERVICE_URL=http://network.railway.internal:8005
# plus NEXT_PUBLIC_SUPABASE_URL / SUPABASE keys from .env (web auth)
```
Services **not** in phase 1 (call_center, support, hr, communication, web_analytics,
customer_journey, billing_collections, fno_intelligence, voicebox) — leave their
`*_SERVICE_URL` unset; those web areas return 503 until phase 2, which is fine.

> Do **not** put secrets in `NEXT_PUBLIC_*`. Only the Supabase publishable key and
> public URLs belong there.

---

## Deploy runbook (phase 1)

Primary path = **GitHub-connected services** (Railway auto-builds on push; per-service
Dockerfile path). CLI is used for the project, Postgres, variables, and schema load.

### 0. One-time
```bash
railway login
cd /c/Users/Benedict/Desktop/OminiDome/omnidome
railway init            # create the "omnidome" project
railway add --database postgres
```

### 1. Load the schema (once)
```bash
# grab the connection string Railway created
railway variables -s Postgres | grep DATABASE_URL
railway run -- psql "$DATABASE_URL" -f config/master_schema.sql
# (or: railway connect Postgres  then \i config/master_schema.sql)
```

### 2. Create each service (dashboard, per row in the core-subset table)
For each service:
1. **New → GitHub Repo → BurniMajozi/omnidome**
2. Settings → Build: **Root Directory `/`**, **Dockerfile Path `services/<x>/Dockerfile`**
   (web uses `apps/web/Dockerfile`).
3. Settings → Deploy → **Custom Start Command**: the `--host ::` uvicorn line
   (see gotcha #1). Skip for `web`.
4. Variables: attach the shared group + any service-specific vars above.
5. `gateway` and `web`: Networking → **Generate Domain** (public). Set gateway target
   port to 8000.

Bring services up in dependency order: **Postgres → admin → (crm, sales, billing,
finance, rica, network, compliance, tenant-memory) → gateway → agent-orchestrator →
web.**

### 3. Wire the public URLs
After `gateway` and `web` have domains, set `web`'s `NEXT_PUBLIC_GATEWAY_URL` and
each service's `CORS_ORIGINS` to the real HTTPS `web` domain, then redeploy `web`.

### 4. Smoke test
- `https://<gateway>/health` → 200
- `https://<web>/` loads, sign in via Supabase, hit a CRM/sales page.
- Check each service's Railway logs for DB-connection success.

---

## Hermes on Railway (cloud agent)

Local Hermes (`hermes_data/`) is **left untouched** — it's actively working the folder.
The cloud Hermes uses **separate** assets under `services/hermes/`:

- `services/hermes/config.railway.yaml` — OpenRouter provider (no Ollama).
- `services/hermes/entrypoint.sh` — on first boot seeds the config into the volume,
  clones `omnidome` into the workspace (or `git pull` if present), then runs the agent.
- `services/hermes/Dockerfile` — `FROM nousresearch/hermes-agent:latest` + the entrypoint.

Deploy:
1. New service → **Deploy from Repo**, Dockerfile Path `services/hermes/Dockerfile`.
2. Attach a **Railway Volume** mounted at `/opt/data` (persists config, auth, cache,
   and the cloned repo workspace).
3. Variables:
   ```
   OPENROUTER_API_KEY=<from .env>
   HERMES_API_KEY=<from .env>
   OMNIDOME_REPO_URL=https://<token>@github.com/BurniMajozi/omnidome.git
   HERMES_MODEL=anthropic/claude-3.5-sonnet   # adjust to taste/cost
   API_SERVER_ENABLED=true
   API_SERVER_HOST=::
   # TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_USERS only if you want the bot
   ```
4. If you want the agent to *push* changes back, use a repo-scoped GitHub token in
   `OMNIDOME_REPO_URL` and confirm the git identity inside `entrypoint.sh`.

> Behaviour change to be aware of: cloud Hermes edits *its own clone* on the volume,
> not your local working copy. It syncs with your machine only through git (push/pull).

---

## Cost sketch (phase 1, ballpark)

~12 small Python services + web + Postgres + Hermes, mostly idle:
Railway bills on actual CPU/RAM usage, so idle FastAPI containers are cheap
(~$3–7/service/mo at low traffic) — call it **~$40–90/mo** for phase 1. The full
~30-service parity is where it climbs to $150–300+, which is why we start with the
subset. Set a **usage limit / budget alert** in Railway before deploying.

---

## Phase 2 checklist (later)
- Add the deferred services the same way (GitHub service + Dockerfile path + `--host ::`).
- Decide voicebox-engine (heavy PyTorch, needs GPU — likely stays off Railway).
- Migrate eCommerce/Medusa per `eCommerce/docs/railway-readiness.md` (Supabase `medusa`
  schema + Railway Redis).
- Revisit LICENSE_ENFORCEMENT (bake license into images) for production posture.
