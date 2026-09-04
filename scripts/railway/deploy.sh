#!/usr/bin/env bash
# OmniDome → Railway phase-1 deploy helper.
#
# Automates the repetitive parts (service creation, per-service variables,
# domains, wiring) so you don't click through the dashboard 13×. It reads the
# per-service env files in ./env/ and resolves secrets from the repo-root .env
# at runtime — no secret is ever written into a committed file.
#
# Prerequisites (one-time, can't be scripted):
#   1. `railway login`
#   2. In the Railway dashboard, authorize the Railway GitHub app for
#      BurniMajozi/omnidome (needed for `railway add --repo`).
#   3. From the repo root: `railway init` (creates the project), then
#      `railway link` if you open a new shell.
#
# Usage:
#   scripts/railway/deploy.sh preflight   # check login/project/.env
#   scripts/railway/deploy.sh db          # provision Railway Postgres + load schema
#   scripts/railway/deploy.sh create      # create all phase-1 services + set vars
#   scripts/railway/deploy.sh domains     # generate public domains (gateway, web)
#   scripts/railway/deploy.sh wire        # fill in domain-dependent vars + redeploy
#   scripts/railway/deploy.sh all         # db → create → domains → wire, in order
#   scripts/railway/deploy.sh create crm  # just one service (create or re-set vars)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$SCRIPT_DIR/env"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOTENV="$REPO_ROOT/.env"
REPO="BurniMajozi/omnidome"
BRANCH="main"

# Creation / deploy order (dependency-aware). web + hermes handled after backends.
BACKENDS=(admin crm sales billing finance rica network compliance tenant-memory agent-orchestrator gateway)
PUBLIC=(gateway web)
# Backends that read CORS_ORIGINS (harmless on the others, but keep it tight).
CORS_SERVICES=(gateway compliance tenant-memory)

log()  { printf '\033[1;36m[railway]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# Look up a key in the repo-root .env, stripping surrounding quotes.
dotenv() {
  local key="$1" val
  [ -f "$DOTENV" ] || die "repo .env not found at $DOTENV"
  val="$(grep -E "^${key}=" "$DOTENV" | head -1 | cut -d= -f2-)" || true
  val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
  printf '%s' "$val"
}

# Resolve one "VALUE" token: @from-dotenv:K -> secret; @web-domain/@gateway-domain
# -> "" (deferred to `wire`); anything else -> literal.
resolve() {
  local raw="$1"
  case "$raw" in
    @from-dotenv:*) dotenv "${raw#@from-dotenv:}" ;;
    @web-domain|@gateway-domain) printf '' ;;   # deferred
    *) printf '%s' "$raw" ;;
  esac
}

# Emit resolved "KEY=VALUE" lines for a service (shared first for backends).
service_vars() {
  local svc="$1" is_backend="$2" files=() f line key val
  [ "$is_backend" = "1" ] && files+=("$ENV_DIR/_shared.env")
  files+=("$ENV_DIR/${svc}.env")
  for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in ''|\#*) continue ;; esac
      key="${line%%=*}"; val="${line#*=}"
      val="$(resolve "$val")"
      [ -z "$val" ] && continue   # skip deferred/empty
      printf '%s=%s\n' "$key" "$val"
    done < "$f"
  done
}

is_backend() { case " ${BACKENDS[*]} " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

get_domain() {  # echo the public host for a service, or nothing
  railway domain list --service "$1" --json 2>/dev/null \
    | grep -oE '[a-z0-9.-]+\.up\.railway\.app' | head -1 || true
}

cmd_preflight() {
  command -v railway >/dev/null || die "railway CLI not found"
  railway whoami >/dev/null 2>&1 || die "not logged in — run: railway login"
  railway status  >/dev/null 2>&1 || die "no project linked — run: railway init (then railway link)"
  [ -f "$DOTENV" ] || die "missing $DOTENV"
  log "preflight OK — logged in, project linked, .env present"
  railway status || true
}

cmd_db() {
  log "provisioning Railway Postgres (skip if it already exists)…"
  railway add --database postgres || warn "postgres add failed/exists — continuing"
  log "load the schema once the DB is up:"
  cat <<EOF
    railway variables --service Postgres --kv | grep DATABASE_URL
    railway run -- psql "\$DATABASE_URL" -f config/master_schema.sql
    # or: railway connect Postgres   then  \\i config/master_schema.sql
EOF
}

create_one() {
  local svc="$1" bflag=0 vargs=() kv
  is_backend "$svc" && bflag=1
  while IFS= read -r kv; do vargs+=(-v "$kv"); done < <(service_vars "$svc" "$bflag")
  log "creating service '$svc' (${#vargs[@]} /2 vars)…"
  if railway add --service "$svc" --repo "$REPO" --branch "$BRANCH" "${vargs[@]}"; then
    log "  created $svc"
  else
    warn "  add failed for $svc (already exists?) — re-applying vars via 'variables set'"
    while IFS= read -r kv; do
      railway variables set "$kv" --service "$svc" --skip-deploys >/dev/null || warn "    set failed: ${kv%%=*}"
    done < <(service_vars "$svc" "$bflag")
  fi
}

cmd_create() {
  if [ "${1:-}" != "" ]; then create_one "$1"; return; fi
  for svc in "${BACKENDS[@]}" web hermes; do create_one "$svc"; done
}

cmd_domains() {
  for svc in "${PUBLIC[@]}"; do
    log "generating domain for $svc…"
    railway domain --service "$svc" || warn "domain gen failed for $svc"
  done
}

cmd_wire() {
  local gw web
  gw="$(get_domain gateway)"; web="$(get_domain web)"
  [ -n "$gw" ]  || die "no gateway domain yet — run: $0 domains"
  [ -n "$web" ] || die "no web domain yet — run: $0 domains"
  log "gateway=https://$gw  web=https://$web"
  log "setting web NEXT_PUBLIC_GATEWAY_URL (triggers web redeploy)…"
  railway variables set "NEXT_PUBLIC_GATEWAY_URL=https://$gw" --service web
  log "setting CORS_ORIGINS=https://$web on: ${CORS_SERVICES[*]}"
  for svc in "${CORS_SERVICES[@]}"; do
    railway variables set "CORS_ORIGINS=https://$web" --service "$svc"
  done
  log "wired. Smoke test: https://$gw/health  and  https://$web/"
}

case "${1:-}" in
  preflight) cmd_preflight ;;
  db)        cmd_preflight; cmd_db ;;
  create)    cmd_preflight; cmd_create "${2:-}" ;;
  domains)   cmd_preflight; cmd_domains ;;
  wire)      cmd_preflight; cmd_wire ;;
  all)       cmd_preflight; cmd_db; cmd_create; cmd_domains; cmd_wire ;;
  *) sed -n '2,30p' "$0"; exit 1 ;;
esac
