---
name: omnidome-session-continuity
description: How to handle session resumption after tool-calling limits, vault usage, and build context gotchas for OmniDome.
version: 1.1.0
---

# OmniDome — Session Continuity & Build Patterns

## Session Resumption (When User Says "Continue")

When the tool-calling limit is hit mid-session and the user says "Continue":

1. **Read vault notes FIRST** to reload context:
   - `~/Documents/Obsidian Vault/OmniDome/Session N.md` (latest session — numbered sequentially, NOT by date)
   - `~/Documents/Obsidian Vault/OmniDome/Implementation Status.md`
   - `~/Documents/Obsidian Vault/OmniDome/To-Do List.md`
2. **Re-read any source files** that were being modified in the previous segment
3. **Pick up from the last completed TODO item** — do NOT re-explain what was already built
4. **Do not re-describe** completed work — just continue building

## Vault as Mid-Term Memory

The Obsidian vault is the agent's persistent memory across sessions:
- **Path:** `~/Documents/Obsidian Vault/OmniDome/`
- **Remote:** `BurniMajozi/Hermes-Obsidian` on GitHub (PAT with repo scope works)
- **Session start:** Read latest session notes + Implementation Status
- **Session end:** Create/update session note, update Implementation Status, `git add -A && git commit && git push origin main` from vault dir
- **Naming:** `Session N.md` (sequential numbering, NOT dates)

## File Write Gotchas (OmniDome-Specific)

1. `~` does NOT expand in `write_file` — always use absolute paths like `/opt/data/home/`
2. Project dir `/opt/data/workspace/omnidome/` is owned by uid 1000 — write patches to `/opt/data/home/omnidome-patches/`
3. **Docker build context:** Files MUST be in `services/<name>/` subdirectory. Writing to `/opt/data/home/omnidome-patches/<name>/` (flat) is NOT enough — Dockerfile COPY starts from `services/`. **Always also copy to `services/<name>/`** and verify with `ls -la services/<name>/`.
4. **Dual-service deploy:** When building 2+ services in one session, write a single `apply-all-patches.sh` that handles ALL services: file copies, __init__.py creation, docker-compose append, .env updates, embedded Python for auto-patching existing files.
5. **Verify writes:** Always `ls -la` the target directory after copying files.

## Git Push Workflow

The main project at `/opt/data/workspace/omnidome/` is NOT a git repository.

**To push project code:**
1. Initialize a git repo in home with worktree pointing to project:
   ```bash
   cd /opt/data/home && git init omnidome-git
   cd omnidome-git && git config core.worktree /opt/data/workspace/omnidome
   ```
2. Stage only tracked files (git add -A times out with 1600+ files):
   ```bash
   git add apps/ services/ config/ docker-compose.yaml ...
   ```
3. Commit and push to remote (requires PAT with `repo` scope for `BurniMajozi/omnidome`)
4. The existing PAT (`ghp_FS...Fxfd`) only has access to `Hermes-Obsidian`, NOT `omnidome`
5. **User must generate a new PAT** with `repo` scope at https://github.com/settings/tokens and provide it

**To push vault notes:**
```bash
cd ~/Documents/Obsidian Vault
git add -A && git commit -m "..." && git push origin main
```

**Always push vault FIRST** (works with current token) before attempting project push.

## Running the Web Portal

**Never assume Docker works.** Always check before attempting:

```bash
# 1. Check Docker daemon
docker info 2>&1 | head -3    # If "Cannot connect to docker daemon" → Docker unavailable
systemctl status docker        # Check daemon status

# 2. Check npm install feasibility
# VM is resource-constrained. npm install for Next.js (~1600 packages) often times out at 300-600s.
# If npm install times out, check partial progress:
ls node_modules/ | wc -l       # < 500 = too few, need complete install
ls node_modules/.bin/next      # If next exists, can try partial build

# 3. next dev (lightweight, no full build) — works on constrained VMs:
npx next dev -p 3000 --hostname 0.0.0.0
# Compiles pages on-demand. Good enough for viewing the UI.
# Run in terminal(background=true), wait ~10s, then curl localhost:3000 to verify.

# 4. next build (production) — likely times out on VM
# Only attempt on local machine or when Docker is available.

# 5. Copy web to home directory for user-writable node_modules:
cp -r apps/web/* /opt/data/home/omnidome-web/   # source only, exclude node_modules
cd /opt/data/home/omnidome-web && npm install --legacy-peer-deps
```

## Cross-Service Bridge Pattern

When service A needs to notify service B of an event:

```python
# In service A (e.g., journey engine cancel_respond):
try:
    import httpx
    service_b_url = os.getenv("SERVICE_B_URL", "http://service_b:PORT")
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(f"{service_b_url}/endpoint", json=payload)
except Exception:
    pass  # Don't fail the caller if the bridge target is down
```

Key: bridge calls are **fire-and-forget** — wrapped in try/except so the calling service succeeds even if the target is down.

## OmniDome Service Map (21 services)

| Service | Port | Purpose |
|---------|------|---------|
| `gateway` | 8000 | API gateway/BFF |
| `crm` | 8001 | Customer 360, leads, segments |
| `sales` | 8002 | Pipeline, deals, quotes, commissions |
| `billing` | 8003 | Invoices, Paystack, collections |
| `rica` | 8004 | RICA identity verification |
| `network` | 8005 | RADIUS, FNO adapters |
| `iot` | 8006 | Device telemetry |
| `call_center` | 8007 | Voice AI, call management |
| `support` | 8008 | Ticketing, SLA |
| `hr` | 8009 | Employee management |
| `inventory` | 8010 | Stock management |
| `analytics` | 8011 | Executive summary, churn analysis |
| `retention` | 8012 | Churn prediction, campaigns |
| `admin` | 8013 | Tenant management, RBAC |
| `marketing` | 8014 | Campaigns, automations |
| `finance` | 8015 | FP&A, scenarios |
| `web_analytics` | 8016 | Website traffic, clicks, forms |
| `journey_engine` | 8017 | Cancel-to-save, rule engine, offers |
| `lifecycle` | 8018 | Customer lifecycle tracking |
| `communication` | 8020 | Chat, messages, tasks |
| `agent-orchestrator` | 8021 | AI agents, tools |

## Cross-Service Integration Map

```
Portal cancel → Journey Engine (8017) → rule matching → offer
                     ↓                              ↓
              Lifecycle (8018) ←──outcome──── Customer stage update
                     ↑
Sales (8002) ──deal close──→ Lifecycle (8018) → stage = Converted
                     ↑
CRM (8001) ←──customer ───── Lifecycle (8018)
```

## Validation Rules (Don't Break These)

See `references/validation-rules.md` for the full checklist. Key rules:

- Every new microservice gets: `models.py`, `main.py`, `database.py`, `requirements.txt`, `Dockerfile`, `routes/` (if applicable)
- Service port allocation: increment from highest existing (currently 8021). Assign 8016+ to new services.
- Frontend proxy route in `apps/web/app/api/<service>/[...path]/route.ts` for Next.js API routing
- Docker Compose addition in `docker-compose-<service>.yaml`
- Environment variable in `.env` for service URL
- Cross-service bridges use fire-and-forget pattern (try/except + pass)
