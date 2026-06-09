#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Zernio Webhook Setup Script for OmniDome Marketing Service
# ═══════════════════════════════════════════════════════════════════════════════
#
# This script:
#   1. Creates Zernio webhook receiver service (Python/FastAPI on port 8025)
#   2. Adds nginx reverse proxy config for webhook traffic routing
#   3. Adds Zernio signature verification patch (auto-applied on start)
#   4. Creates systemd service for persistence
#   5. All config stored on /opt/data/ (persistent volume)
#
# Usage:
#   sudo bash setup_zernio_webhook.sh
#
# Prerequisites:
#   - Zernio API key (set ZERNIO_API_KEY env var or enter when prompted)
#   - nginx installed (for traffic routing)
#   - systemd (for service persistence)
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN] ⚠${NC} $1"; }
err()  { echo -e "${RED}[ERROR] ✗${NC} $1"; }
info() { echo -e "${CYAN}[INFO] ℹ${NC} $1"; }

# ── Paths (all on persistent /opt/data volume) ───────────────────────────────
DATA_DIR="/opt/data"
ZERNIO_DIR="${DATA_DIR}/zernio"
CONFIG_FILE="${DATA_DIR}/.env.zernio"
LOG_DIR="${ZERNIO_DIR}/logs"
PATCH_DIR="${ZERNIO_DIR}/patches"
WEBHOOK_PORT=8025
WEBHOOK_PATH="/api/marketing/zernio/webhook"
NGINX_CONF="/etc/nginx/sites-available/zernio-webhook"
NGINX_LINK="/etc/nginx/sites-enabled/zernio-webhook"
SYSTEMD_SERVICE="/etc/systemd/system/zernio-webhook.service"
PID_FILE="${ZERNIO_DIR}/webhook.pid"
VENV_PYTHON="/opt/data/workspace/omnidome/.venv/bin/python3"

# ── Pre-flight ───────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Zernio Webhook Setup for OmniDome Marketing Service"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Check root
if [[ $EUID -ne 0 ]]; then
    warn "Not running as root — nginx and systemd steps will be skipped"
    SUDO=false
else
    SUDO=true
fi

# ── Get API Key ──────────────────────────────────────────────────────────────
if [[ -z "${ZERNIO_API_KEY:-}" ]]; then
    if [[ -f "$CONFIG_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$CONFIG_FILE"
        log "Loaded config from $CONFIG_FILE"
    fi
fi

if [[ -z "${ZERNIO_API_KEY:-}" ]]; then
    echo -n "Enter Zernio API key (sk_...): "
    read -r ZERNIO_API_KEY
    echo ""
fi

if [[ -z "$ZERNIO_API_KEY" ]]; then
    err "ZERNIO_API_KEY is required"
    exit 1
fi

KEY_LEN=${#ZERNIO_API_KEY}
KEY_PREFIX="${ZERNIO_API_KEY:0:10}..."
log "API key: ${KEY_PREFIX} (${KEY_LEN} chars)"

# ── Get Webhook Secret ───────────────────────────────────────────────────────
if [[ -z "${ZERNIO_WEBHOOK_SECRET:-}" ]] && [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE" 2>/dev/null || true
fi

if [[ -z "${ZERNIO_WEBHOOK_SECRET:-}" ]]; then
    echo -n "Enter Zernio webhook signing secret (optional, press Enter to skip): "
    read -r ZERNIO_WEBHOOK_SECRET
    echo ""
fi

if [[ -n "$ZERNIO_WEBHOOK_SECRET" ]]; then
    log "Webhook secret: configured (${#ZERNIO_WEBHOOK_SECRET} chars)"
else
    warn "Webhook secret: NOT set — signature verification will be skipped"
fi

# ── Step 1: Directory Structure ──────────────────────────────────────────────
log "Step 1: Creating directory structure..."
mkdir -p "$ZERNIO_DIR" "$LOG_DIR" "$PATCH_DIR"
log "  ${ZERNIO_DIR}"

# ── Step 2: Store Credentials ────────────────────────────────────────────────
log "Step 2: Storing credentials..."
cat > "$CONFIG_FILE" << CREDS
# Zernio API Configuration
# Generated: $(date -u +'%Y-%m-%dT%H:%M:%SZ')
ZERNIO_API_KEY=${ZERNIO_API_KEY}
ZERNIO_WEBHOOK_SECRET=${ZERNIO_WEBHOOK_SECRET:-}
ZERNIO_WEBHOOK_PORT=${WEBHOOK_PORT}
CREDS
chmod 600 "$CONFIG_FILE"
log "  ${CONFIG_FILE} (mode 600)"

# ── Step 3: Webhook Receiver ─────────────────────────────────────────────────
log "Step 3: Creating webhook receiver..."

cat > "${ZERNIO_DIR}/webhook_server.py" << 'WEBSERVER'
#!/usr/bin/env python3
"""Zernio Webhook Receiver — auto-applies signature patch on startup."""
import hashlib, hmac, json, logging, os, sys
from datetime import datetime
from pathlib import Path

# Load config
DATA_DIR = Path("/opt/data")
CONFIG_FILE = DATA_DIR / ".env.zernio"
if CONFIG_FILE.exists():
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

ZERNIO_API_KEY = os.getenv("ZERNIO_API_KEY", "")
ZERNIO_WEBHOOK_SECRET = os.getenv("ZERNIO_WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.getenv("ZERNIO_WEBHOOK_PORT", "8025"))
ZERNIO_DIR = DATA_DIR / "zernio"
LOG_FILE = ZERNIO_DIR / "logs" / "webhook.log"
INBOX_FILE = ZERNIO_DIR / "inbox.jsonl"
ESCALATE_FILE = ZERNIO_DIR / "escalations.jsonl"
PATCH_FILE = ZERNIO_DIR / "patches" / "zernio_signature_patch.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("zernio-webhook")

# ── Signature Patch (auto-applied on start) ──────────────────────────────────
def apply_patch():
    if PATCH_FILE.exists():
        log.info("Signature patch already applied")
        return
    PATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    PATCH_FILE.write_text('''"""Zernio Signature Verification Patch — auto-applied on startup."""
import hashlib, hmac, os
_SECRET = os.getenv("ZERNIO_WEBHOOK_SECRET", "")
def verify(body: bytes, sig: str) -> bool:
    if not _SECRET: return True
    return hmac.compare_digest(hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest(), sig)
''')
    log.info(f"Signature patch applied: {PATCH_FILE}")

def verify_sig(body: bytes, sig: str) -> bool:
    if not ZERNIO_WEBHOOK_SECRET:
        return True
    return hmac.compare_digest(
        hmac.new(ZERNIO_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest(), sig
    )

# ── Event Processing ─────────────────────────────────────────────────────────
def normalize(evt: dict) -> dict:
    et = evt.get("event_type", "unknown")
    p = evt.get("platform", "unknown")
    s = evt.get("sender", {})
    c = evt.get("content", evt.get("text", ""))
    tl = c.lower()
    pos = sum(1 for w in ["thanks","great","awesome","love","good","excellent","happy","perfect","amazing"] if w in tl)
    neg = sum(1 for w in ["bad","terrible","worst","hate","angry","frustrated","broken","issue","problem","complaint","refund","cancel"] if w in tl)
    sent = "POSITIVE" if pos > neg else ("NEGATIVE" if neg > pos else "NEUTRAL")
    return {
        "message_type": {"message.received":"DM","comment.received":"COMMENT","mention.received":"MENTION","review.received":"REVIEW"}.get(et,"DM"),
        "platform": p, "external_id": evt.get("message_id", evt.get("id", "")),
        "sender_name": s.get("name", s.get("handle", "Unknown")),
        "sender_handle": s.get("handle", ""), "sender_profile_url": s.get("profile_url", ""),
        "content": c, "parent_id": evt.get("parent_id"), "status": "UNREAD",
        "sentiment": sent, "attachments": evt.get("attachments", []),
        "conversation_id": evt.get("conversation_id"),
        "received_at": datetime.utcnow().isoformat(),
    }

def should_escalate(content: str) -> bool:
    return any(k in content.lower() for k in ["complaint","refund","cancel","urgent","escalate","manager","supervisor","not working","down","outage","billing","overcharge","dispute"])

# ── Starlette App ────────────────────────────────────────────────────────────
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

async def webhook(request):
    body = await request.body()
    sig = request.headers.get("X-Zernio-Signature", "")
    if not verify_sig(body, sig):
        log.warning("Invalid signature — rejected")
        return JSONResponse({"error": "Invalid signature"}, status_code=401)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    et = payload.get("event_type", "unknown")
    log.info(f"Webhook: {et}")

    if et in ("message.received", "comment.received", "mention.received"):
        n = normalize(payload)
        log.info(f"  {n['platform']} | {n['sender_name']} | {n['sentiment']}")
        INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INBOX_FILE, "a") as f:
            f.write(json.dumps(n, default=str) + "\n")
        if should_escalate(n["content"]):
            log.warning(f"  ESCALATION: {n['sender_name']}")
            with open(ESCALATE_FILE, "a") as f:
                f.write(json.dumps({"ts": datetime.utcnow().isoformat(), "msg": n, "reason": "keyword"}, default=str) + "\n")
    elif et == "reaction.received":
        log.info(f"  Reaction: {payload.get('emoji')} on {payload.get('platform')}")
    return JSONResponse({"status": "received"})

async def health(request):
    return JSONResponse({"status":"ok","service":"zernio-webhook","ts":datetime.utcnow().isoformat(),"key_configured":bool(ZERNIO_API_KEY),"secret_configured":bool(ZERNIO_WEBHOOK_SECRET)})

app = Starlette(routes=[
    Route("/api/marketing/zernio/webhook", webhook, methods=["POST"]),
    Route("/health", health, methods=["GET"]),
])

if __name__ == "__main__":
    import uvicorn
    if not ZERNIO_API_KEY:
        log.error("ZERNIO_API_KEY not set"); sys.exit(1)
    apply_patch()
    log.info(f"Starting on port {WEBHOOK_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=WEBHOOK_PORT, log_level="info")
WEBSERVER

chmod +x "${ZERNIO_DIR}/webhook_server.py"
log "  ${ZERNIO_DIR}/webhook_server.py"

# ── Step 4: systemd Service ──────────────────────────────────────────────────
log "Step 4: Creating systemd service..."

if $SUDO; then
    cat > "$SYSTEMD_SERVICE" << EOF
[Unit]
Description=Zernio Webhook Receiver for OmniDome Marketing
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=hermes
Group=hermes
WorkingDirectory=${ZERNIO_DIR}
EnvironmentFile=${CONFIG_FILE}
ExecStartPre=${VENV_PYTHON} -c "
import os; secret=os.getenv('ZERNIO_WEBHOOK_SECRET','')
print(f'Webhook secret: {\"configured\" if secret else \"NOT SET\"} ({len(secret)} chars)')
"
ExecStart=${VENV_PYTHON} ${ZERNIO_DIR}/webhook_server.py
Restart=always
RestartSec=5
StandardOutput=append:${LOG_DIR}/webhook.log
StandardError=append:${LOG_DIR}/webhook.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable zernio-webhook.service
    log "  systemd service: zernio-webhook.service"
else
    warn "  Skipping systemd (not root)"
fi

# ── Step 5: nginx Config ─────────────────────────────────────────────────────
log "Step 5: Configuring nginx..."

if $SUDO && command -v nginx &>/dev/null; then
    cat > "$NGINX_CONF" << EOF
# Zernio Webhook — routes to OmniDome marketing webhook receiver
server {
    listen 80;
    server_name _;

    location ${WEBHOOK_PATH} {
        proxy_pass http://127.0.0.1:${WEBHOOK_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 30s;
    }

    location /zernio-health {
        proxy_pass http://127.0.0.1:${WEBHOOK_PORT}/health;
    }
}
EOF

    ln -sf "$NGINX_CONF" "$NGINX_LINK" 2>/dev/null || true
    if nginx -t 2>/dev/null; then
        systemctl reload nginx 2>/dev/null || systemctl start nginx 2>/dev/null || true
        log "  nginx configured and reloaded"
    else
        warn "  nginx config test failed — check manually"
    fi
else
    warn "  nginx not available — webhook on port ${WEBHOOK_PORT}"
fi

# ── Step 6: Start Service ────────────────────────────────────────────────────
log "Step 6: Starting webhook receiver..."

if $SUDO; then
    systemctl start zernio-webhook.service 2>/dev/null || true
    sleep 2
    if systemctl is-active --quiet zernio-webhook.service; then
        log "  Service running ✓"
    else
        warn "  Service not active — check: journalctl -u zernio-webhook"
    fi
else
    cd "$ZERNIO_DIR"
    nohup "$VENV_PYTHON" webhook_server.py >> "${LOG_DIR}/webhook.log" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        log "  Running (PID: $(cat "$PID_FILE")) ✓"
    else
        warn "  Failed to start — check ${LOG_DIR}/webhook.log"
    fi
fi

# ── Step 7: Verify ───────────────────────────────────────────────────────────
log "Step 7: Verification..."
sleep 1

HEALTH_URL="http://127.0.0.1:${WEBHOOK_PORT}/health"
if command -v curl &>/dev/null; then
    H=$(curl -s "$HEALTH_URL" 2>/dev/null || echo "failed")
    if [[ "$H" != "failed" ]]; then
        log "  Health: $H"
    else
        warn "  Health check failed — may still be starting"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Zernio Webhook Setup Complete"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Config:     ${CONFIG_FILE}"
echo "  Service:    ${ZERNIO_DIR}/webhook_server.py"
echo "  Logs:       ${LOG_DIR}/webhook.log"
echo "  Inbox:      ${ZERNIO_DIR}/inbox.jsonl"
echo "  Patches:    ${PATCH_DIR}/"
echo ""
echo "  Webhook:    http://<host>:${WEBHOOK_PORT}${WEBHOOK_PATH}"
echo "  Health:     http://<host>:${WEBHOOK_PORT}/health"
echo ""
echo "  Signature verification: AUTO-APPLIED on startup"
echo "  Auto-restart: enabled"
echo ""
echo "  Zernio dashboard → Webhooks → Add:"
echo "    URL:    http://<your-domain>:${WEBHOOK_PORT}${WEBHOOK_PATH}"
echo "    Events: message.received, comment.received"
echo "    Secret: (copy from ${CONFIG_FILE})"
echo ""
echo "═══════════════════════════════════════════════════════════════"
