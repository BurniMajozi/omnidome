# Subagent File Creation Patterns

> Learned from OmniDome multi-service implementation. 2026-05-31.

## The 600s Timeout Wall

`delegate_task` has a hard 600s timeout. Tasks creating many files WILL time out.

### What timed out
- Creating 17 files for the communication service (routes/__init__.py + 7 route files + models + schemas + main.py + database.py + Dockerfile + requirements.txt)
- Creating 19 files for the agent-orchestrator service
- Tasks that ask subagents to "create all files for service X" when >15 files needed

### What worked
- Splitting into smaller batches (e.g., routes in one subagent, models+schemas in another)
- Creating the main.py + models + schemas via subagent, then writing route files directly in the main session
- Using `write_file` directly in the main session for boilerpler files
- Single subagent per service directory (no sibling conflicts)

### Rules of Thumb

| File Count | Approach |
|-----------|----------|
| **1-5 files** | Direct `write_file` in main session |
| **6-12 files** | Single subagent, focused scope |
| **13-20 files** | Split: 1 subagent for routes, 1 for models/schemas, or do it in main session |
| **20+ files** | Always split across multiple subagents or do in main session |

## Sibling Subagent Conflicts

When two subagents write to the same directory, the second one gets `_WARNING: file was modified by sibling subagent_`. This is a data loss risk.

**Rule: each subagent gets its own directory.** If you need 3 subagents for one service, partition by subdirectory:
- Subagent A: `services/X/models.py`, `services/X/schemas.py`, `services/X/main.py`
- Subagent B: `services/X/routes/` (all route files)
- Subagent C: `services/X/channels/` or `services/X/tools/`

## Subagent prompts that work

```python
delegate_task(
    goal="Create route files for X service",
    context="""
    Create these exact files:
    1. services/X/routes/__init__.py
    2. services/X/routes/customers.py (CRUD with pagination, async DB)
    3. ...
    
    PATTERNS to use:
    - Import AuthContext and get_auth_context from services.common.auth
    - Use async session_scope from services.common.db
    - Every write must include tenant_id from ctx
    - Return appropriate HTTP status codes
    
    DO NOT touch main.py or models.py — those are handled separately.
    """,
    toolsets=["file"]
)
```

Key: tell subagents what NOT to touch, give exact file listings, and provide pattern examples.
