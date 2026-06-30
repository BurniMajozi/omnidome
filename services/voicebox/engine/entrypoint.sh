#!/bin/sh
# The voicebox_models named volume is created root-owned by Docker on first
# mount, but the engine process runs as the non-root `voicebox` user — so
# without this, the first model download fails with PermissionError on
# /data/models. Container starts as root (see Dockerfile), fixes ownership
# of whatever's actually mounted there, then drops to voicebox via gosu.
set -e
chown -R voicebox:voicebox /data/models 2>/dev/null || true
exec gosu voicebox "$@"
