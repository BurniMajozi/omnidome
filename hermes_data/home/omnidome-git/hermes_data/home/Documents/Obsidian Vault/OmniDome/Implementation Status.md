# OmniDome — Implementation Status

> Current state of all OmniDome microservices as of 2026-06-01 (Session 4).

## Services Implemented

| Service | Port | Status | Session |
|---------|------|--------|---------|
| `gateway` | 8000 | ✅ | 1 |
| `crm` | 8001 | 🟡 | 1 |
| `sales` | 8002 | 🟡 | — |
| `billing` | 8003 | 🟡 | 2 |
| `rica` | 8004 | 🟡 | 2 |
| `network` | 8005 | 🟡 | — |
| `iot` | 8006 | 🟡 | 2 |
| `call_center` | 8007 | 🟡 | 2 |
| `support` | 8008 | ✅ | 1 |
| `hr` | 8009 | 🟡 | 2 |
| `inventory` | 8010 | 🟡 | — |
| `analytics` | 8011 | ✅ | 1 |
| `retention` | 8012 | 🟡 | 2 |
| `admin` | 8013 | 🟡 | — |
| `marketing` | 8014 | 🟡 | 2 |
| `finance` | 8015 | 🟡 | 2 |
| `web_analytics` | 8016 | ✅ | 3 |
| `journey_engine` | 8017 | ✅ | 3 |
| `lifecycle` | 8018 | ✅ | 4 |
| `communication` | 8020 | ✅ | 1 |
| `agent-orchestrator` | 8021 | ✅ | 1 |

## Cross-Service Integration Map

```
Portal cancel → Journey Engine (8017) → rule matching → offer
                     ↓                              ↓
              Lifecycle (8018) ←──outcome──── Customer stage update
                     ↑
Sales (8002) ──deal close──→ Lifecycle (8018) → stage = Converted
                     ↑
CRM (8001) ←──customer record───────────── Lifecycle (8018)
```

## Key Architecture Decisions

1. **Journey Engine rule engine** — AND within rule groups, OR across groups, priority-based selection
2. **Lifecycle service** — centralized state machine for all customer stage transitions
3. **Cross-service bridges** — async HTTP calls between journey, lifecycle, and sales services
4. **POPIA compliance** — IP hashing in analytics, tenant isolation via ContextVar, on-prem Ollama

## Next Steps

### Immediate (P0)
1. Apply all patches: `bash omnidome-patches/apply-all-patches.sh`
2. Rebuild: `docker compose up -d --build journey_engine web_analytics lifecycle`
3. Wire portal cancel button → Journey Engine

### Short-term (P1)
4. Convert Sales service raw SQL → async SQLAlchemy
5. Add CRM 360 lifecycle panel
6. Sales → Lifecycle bridge (deal close-won)
7. Journey Engine outcome batch job (90d/180d flags)

### Medium-term (P2)
8. Lifecycle A/B testing UI
9. Custom analytics dashboards
10. Real FNO adapters (Vumatel + Openserve)

## File Locations

All implementation files: `/opt/data/home/omnidome-patches/`
All Obsidian notes: `~/Documents/Obsidian Vault/OmniDome/`
Project source: `/opt/data/workspace/omnidome/`

## Related Notes
- [[OmniDome — Agentic Architecture]]
- [[OmniDome — Session 2026-05-31]]
- [[OmniDome — Session 2026-06-01]]
- [[OmniDome — Session 4]]
