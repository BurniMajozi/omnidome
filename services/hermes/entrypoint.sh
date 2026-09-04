#!/usr/bin/env sh
# Cloud Hermes bootstrap for Railway.
# Volume is mounted at /opt/data (persists across deploys). On first boot the
# volume is empty, so we seed the config and clone the repo; on later boots we
# just refresh the repo and start.
set -eu

DATA_DIR="${HERMES_DATA_DIR:-/opt/data}"
WORKSPACE="${DATA_DIR}/workspace"
REPO_DIR="${WORKSPACE}/omnidome"
CONFIG_DST="${DATA_DIR}/config.yaml"
CONFIG_SRC="/opt/hermes-seed/config.railway.yaml"

mkdir -p "$WORKSPACE"

# 1. Seed config only if the volume doesn't already have one (don't clobber edits).
if [ ! -f "$CONFIG_DST" ]; then
  echo "[entrypoint] seeding config -> $CONFIG_DST"
  cp "$CONFIG_SRC" "$CONFIG_DST"
  # Let HERMES_MODEL override the default model at seed time.
  if [ -n "${HERMES_MODEL:-}" ]; then
    sed -i "s#^  default: .*#  default: ${HERMES_MODEL}#" "$CONFIG_DST"
  fi
fi

# 2. Clone or update the working repo the agent operates on.
if [ -z "${OMNIDOME_REPO_URL:-}" ]; then
  echo "[entrypoint] OMNIDOME_REPO_URL not set — skipping repo checkout" >&2
elif [ -d "${REPO_DIR}/.git" ]; then
  echo "[entrypoint] updating existing repo at $REPO_DIR"
  git -C "$REPO_DIR" pull --ff-only || echo "[entrypoint] git pull failed (continuing)" >&2
else
  echo "[entrypoint] cloning repo -> $REPO_DIR"
  git clone --depth 1 "$OMNIDOME_REPO_URL" "$REPO_DIR" || echo "[entrypoint] git clone failed (continuing)" >&2
fi

# 3. Git identity for any commits the agent makes.
git config --global user.email "${GIT_AUTHOR_EMAIL:-hermes@omnidome.local}"
git config --global user.name  "${GIT_AUTHOR_NAME:-Hermes Agent}"
git config --global --add safe.directory "$REPO_DIR" || true

# 4. Hand off to the agent gateway.
echo "[entrypoint] starting hermes gateway"
exec gateway run
