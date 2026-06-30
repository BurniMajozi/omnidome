#!/bin/sh
# Named volumes (voicebox_models, voicebox_data) are created root-owned by
# Docker on first mount, but the engine process runs as the non-root
# `voicebox` user — so without this, the first model download (or any
# write to the SQLite db / generations / profile samples) fails with
# PermissionError. Container starts as root (see Dockerfile), fixes
# ownership of whatever's actually mounted, then drops to voicebox via gosu.
set -e
chown -R voicebox:voicebox /data/models /app/data 2>/dev/null || true
exec gosu voicebox "$@"
