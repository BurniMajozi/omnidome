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

# API server for the agent (matches local API_SERVER_* usage); bind IPv6 so it
# is reachable over Railway private networking if you expose it.
ENV API_SERVER_ENABLED=true \
    API_SERVER_HOST=:: \
    HERMES_DATA_DIR=/opt/data

ENTRYPOINT ["/usr/local/bin/hermes-entrypoint.sh"]
