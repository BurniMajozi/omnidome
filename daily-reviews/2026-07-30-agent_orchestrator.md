# Daily Review — 2026-07-30 — services/agent_orchestrator

## Today's plan
Reviewed **services/agent_orchestrator** (rotation position 7 of 35; previous: admin, 2026-07-24).
Scope: config, main app, LLM clients (legacy + Hermes), agent loop, tools, voice client, MCP route.

## What was found / achieved
**Duplicated & divergent model routing**
- `llm.py:17-23` defines its own `MODEL_ROUTES` separate from `config.py:36-42` `model_routes`. They disagree: config uses real OpenRouter model IDs, but `llm.py` falls back to `"openrouter/owl-alpha"` for every agent type — almost certainly a placeholder/nonexistent model ID that will 404 on OpenRouter.
- `llm.py:246` `chat_stream` default fallback is `"openrouter/ollama"` — also a bogus model string.

**Config bypassed / inconsistent defaults**
- `llm.py:12` reads `OLLAMA_BASE_URL` env directly (default `http://127.0.0.1:11434`) while `config.py:20` says `http://ollama:11434` — two sources of truth; in Docker, the llm.py default is wrong unless env is set.
- `llm.py:201` hardcoded `HTTP-Referer: "https://omnidome.local"` in OpenRouter calls.
- `config.py:47` DB default `postgresql://postgres:postgres@localhost:5432/omnidome` — dev creds as fallback; fine only if env always set in prod.

**Auth gaps**
- `routes/mcp.py:96-99` `_check_auth` silently allows ALL requests when `hermes_api_key` is empty — and empty is the default (`config.py:31`). Combined with `/mcp/` being in `public_paths` (main.py:34), the MCP tool-execution endpoint is effectively unauthenticated out of the box.

**Robustness**
- `llm.py:74-84` `_check_ollama` caches availability forever (per-process); if Ollama restarts or comes up later, the service never re-detects it.
- `agents.py:136-141` tool results fed back as `role: "tool"` without `tool_call_id`/name — works for Ollama, will be rejected or mis-associated by OpenAI-format APIs (OpenRouter fallback path).
- `agents.py` failure of the LLM mid-loop returns a canned apology; tool errors are passed through but there's no retry/backoff.

**Positives**
- No mock/stub data arrays, no TODO/FIXME markers found; error handling in `voice_client.py` and `hermes_client.py` is solid; tool execution has timeouts and structured error returns; startup table creation is env-gated.

## Critical decisions / flags
1. **`openrouter/owl-alpha` fallback model** — placeholder or intentional alias? Decide the real OpenRouter fallback models and delete the duplicate `MODEL_ROUTES` in llm.py in favour of `settings.model_routes`.
2. **Hermes MCP auth** — should an empty `hermes_api_key` fail closed (401) instead of open? Recommended for prod; needs a decision on how Hermes gets its token provisioned.
3. **Legacy vs Hermes chat backend** — `chat_backend: "hermes"` is default with legacy kept as rollback; confirm whether legacy llm.py path still needs maintenance or can be removed.

## Tomorrow's component
**services/analytics** (8 of 35).
