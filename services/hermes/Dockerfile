# Cloud Hermes image for Railway. Thin layer over the upstream agent image that
# adds git (for the repo checkout) and our bootstrap entrypoint.
#
# The Railway volume mounts at /opt/data at RUNTIME and overlays anything baked
# there, so the seed config is staged at /opt/hermes-seed and copied into the
# volume by entrypoint.sh on first boot.
FROM nousresearch/hermes-agent:latest

USER root
# git for repo checkout; the base image already carries the agent runtime.
RUN (apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
     && rm -rf /var/lib/apt/lists/*) \
  || (apk add --no-cache git ca-certificates) \
  || true

COPY services/hermes/config.railway.yaml /opt/hermes-seed/config.railway.yaml
COPY services/hermes/entrypoint.sh /usr/local/bin/hermes-entrypoint.sh
RUN chmod +x /usr/local/bin/hermes-entrypoint.sh

# API server bound to LOOPBACK only. We interact via Telegram, so the HTTP API
# stays internal (not network-accessible) — this closes the unsandboxed-RCE
# surface Hermes warns about. To expose it later, override API_SERVER_HOST to ::
# on the service and generate a domain (accept the RCE risk / sandbox first).
ENV API_SERVER_ENABLED=true \
    API_SERVER_HOST=127.0.0.1 \
    HERMES_DATA_DIR=/opt/data

ENTRYPOINT ["/usr/local/bin/hermes-entrypoint.sh"]
