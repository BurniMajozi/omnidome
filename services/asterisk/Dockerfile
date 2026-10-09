# Asterisk 20 LTS (Debian bookworm package) for the OmniDome Call Center.
#
# Pinned to the 20.x LTS series. For a byte-exact pin, replace ASTERISK_VERSION with the full Debian
# version string (`apt-cache madison asterisk` inside the base image) and the base image with a digest.
FROM debian:bookworm-slim

ARG ASTERISK_VERSION=1:20.*

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      "asterisk=${ASTERISK_VERSION}" "asterisk-modules=${ASTERISK_VERSION}" \
      asterisk-core-sounds-en asterisk-moh-opsound-wav \
      python3-minimal ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

# Our templates overwrite the matching package defaults (pjsip/http/ari/rtp/modules/...) at start,
# rendered from env; the remaining packaged defaults (asterisk.conf, musiconhold.conf...) are kept.
COPY templates/ /opt/omnidome/templates/
COPY render.py admin.py /opt/omnidome/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh \
 && mkdir -p /etc/asterisk/generated /var/spool/asterisk/recording \
 && chown -R asterisk:asterisk /etc/asterisk /var/spool/asterisk /var/lib/asterisk /var/log/asterisk /var/run/asterisk

# Internal only: 8088 = ARI + SIP-over-WebSocket (plain; TLS is terminated by the reverse proxy),
# 8099 = admin sidecar (bearer-token protected, reload/status only). NEVER publish these.
# SIP/RTP below are published only on a public VPS (see docs/call-center-telephony.md).
EXPOSE 8088 8099
EXPOSE 5060/udp 5060/tcp
EXPOSE 10000-10100/udp

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD asterisk -rx "core show uptime" >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
