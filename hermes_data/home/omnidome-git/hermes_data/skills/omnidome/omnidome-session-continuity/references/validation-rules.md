# OmniDome — Validation Rules

## New Microservice Checklist

Every new microservice MUST have:

```
services/<name>/
├── __init__.py          # Empty, marks as Python package
├── models.py            # SQLAlchemy models
├── database.py          # Async session management
├── main.py              # FastAPI app with routes
├── requirements.txt     # -r ../common/requirements.txt + extras
├── Dockerfile           # Python 3.12-slim, port
```

## Frontend Integration Checklist

```
apps/web/
├── app/api/<service>/[...path]/route.ts   # Proxy to backend
├── lib/<service>-api.ts                   # Typed API client
└── components/modules/<service>/<service>-dashboard.tsx  # UI
```

## Port Allocation

- 8000-8015: Original services
- 8016-8021: Session 3-4 services (web_analytics, journey_engine, lifecycle, etc.)
- 8022+: Next available

## Cross-Service Bridge Pattern

Bridge calls are fire-and-forget:

```python
try:
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(f"{target_url}/endpoint", json=payload)
except Exception:
    pass  # Never fail the caller
```

## Git Push

- Vault: `cd ~/Documents/Obsidian Vault && git add -A && git commit && git push`
- Project: requires PAT with repo scope (current PAT only works for Hermes-Obsidian)
