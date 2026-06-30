# syntax=docker/dockerfile:1.4
# ============================================================
# Voicebox ML Engine — vendored from https://github.com/jamiepine/voicebox
# (MIT licensed; see ./LICENSE). Backend-only build: the upstream Tauri
# desktop shell and bundled web UI are dropped — OmniDome's own UI talks
# to this engine through services/voicebox (the thin tenant-aware adapter
# in front of it), not through voicebox's own frontend.
#
# HEAVY IMAGE: pulls PyTorch + transformers + multiple TTS engines.
# Not part of the default `docker compose up` — see the `voicebox-engine`
# service definition in docker-compose.yaml (gated behind a compose
# `profiles` entry) and VOICEBOX_MODELS_DIR for where weights land on
# first run (multi-GB download, not included in this image).
#
# pip installs use a BuildKit cache mount: on a flaky connection, a
# retried `docker compose build` resumes from already-downloaded wheels
# instead of redownloading several GB of packages from scratch.
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip

COPY backend/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 60 --prefix=/install -r requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 60 --prefix=/install --no-deps chatterbox-tts
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 60 --prefix=/install --no-deps hume-tada
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 60 --prefix=/install \
    git+https://github.com/QwenLM/Qwen3-TTS.git

FROM python:3.11-slim

RUN groupadd -r voicebox && useradd -r -g voicebox -m -s /bin/bash voicebox

WORKDIR /app

# gosu drops root privileges after entrypoint.sh fixes up the (possibly
# root-owned, freshly-mounted) /data/models volume — see entrypoint.sh.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --chown=voicebox:voicebox backend/ /app/backend/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /app/data/generations /app/data/profiles /app/data/cache \
    && chown -R voicebox:voicebox /app/data

# Stays root so entrypoint.sh can chown the mounted volume before dropping
# to voicebox via gosu — do not add `USER voicebox` here.

EXPOSE 17493

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:17493/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "17493"]
