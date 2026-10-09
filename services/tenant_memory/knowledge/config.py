"""Environment-driven settings for the knowledge layer (read lazily so tests can monkeypatch env)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    knowledge_db_url: str
    embedding_model: str
    embedding_dim: int
    ollama_base_url: str
    doc_prefix: str
    query_prefix: str
    embed_batch_size: int
    embed_timeout_s: float
    embed_retries: int
    index_batch_size: int
    index_concurrency: int
    index_sleep_s: float
    reconcile_hours: int
    poll_seconds: int
    chunk_chars: int
    chunk_overlap: int
    hnsw_m: int
    hnsw_ef_construction: int
    hnsw_ef_search: int
    working_ttl_minutes: int
    max_graph_depth: int


def get_settings() -> Settings:
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    nomic = model.startswith("nomic-embed")
    return Settings(
        knowledge_db_url=os.getenv("KNOWLEDGE_DB_URL", "").strip(),
        embedding_model=model,
        embedding_dim=_int("EMBEDDING_DIM", 768),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "http://ollama:11434")).rstrip("/"),
        # nomic-embed-text is trained with task prefixes; other models use none.
        doc_prefix=os.getenv("EMBEDDING_DOC_PREFIX", "search_document: " if nomic else ""),
        query_prefix=os.getenv("EMBEDDING_QUERY_PREFIX", "search_query: " if nomic else ""),
        embed_batch_size=_int("EMBED_BATCH_SIZE", 16),
        embed_timeout_s=_float("EMBED_TIMEOUT_S", 60.0),
        embed_retries=_int("EMBED_RETRIES", 2),
        index_batch_size=_int("INDEX_BATCH_SIZE", 50),
        index_concurrency=max(1, min(2, _int("INDEX_CONCURRENCY", 1))),
        index_sleep_s=_float("INDEX_SLEEP_S", 1.0),
        reconcile_hours=_int("INDEX_RECONCILE_HOURS", 24),
        poll_seconds=_int("INDEX_POLL_SECONDS", 30),
        chunk_chars=_int("CHUNK_CHARS", 1800),
        chunk_overlap=_int("CHUNK_OVERLAP", 150),
        hnsw_m=_int("HNSW_M", 12),
        hnsw_ef_construction=_int("HNSW_EF_CONSTRUCTION", 48),
        hnsw_ef_search=_int("HNSW_EF_SEARCH", 40),
        working_ttl_minutes=_int("WORKING_MEMORY_TTL_MINUTES", 240),
        max_graph_depth=min(4, _int("GRAPH_MAX_DEPTH", 3)),
    )


def knowledge_enabled() -> bool:
    return bool(get_settings().knowledge_db_url) and _bool("KNOWLEDGE_ENABLED", True)
