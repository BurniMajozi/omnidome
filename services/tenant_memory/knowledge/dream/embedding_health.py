"""Phase 2 - EMBEDDING HEALTH & DRIFT.

* scan stored vectors (rotating, resumable): missing / wrong dimension / NaN / zero / outlier norm, duplicate vectors,
  rows embedded by an older model; re-embed the bad ones from the stored text (rate limited, derived data only);
* semantic drift: cosine distance between the old and new embedding of every card phase 1 refreshed;
* canary retrieval probe: the titles of the tenant's most important cards must retrieve their own card in the top 3.
"""
from __future__ import annotations

import hashlib
import math
import re
import statistics

from services.tenant_memory.knowledge.cards.base import stable_text
from services.tenant_memory.knowledge.dream.context import PhaseCtx
from services.tenant_memory.knowledge.embeddings import EmbeddingError, cosine
from services.tenant_memory.knowledge.kdata import AccessScope, Filters, content_hash
from services.tenant_memory.knowledge.retrieval import KnowledgeRetriever

CURSOR_KEY = ("__dream__", "embed_cursor")
_PART = re.compile(r"\s*\(part \d+/\d+\)\s*$")


def vector_problem(vec, dim: int) -> str | None:
    """'missing' | 'bad_dim' | 'invalid' (NaN/inf/zero) | None. Pure."""
    if vec is None or len(vec) == 0:
        return "missing"
    if len(vec) != dim:
        return "bad_dim"
    if any((not isinstance(x, (int, float))) or math.isnan(x) or math.isinf(x) for x in vec):
        return "invalid"
    if math.sqrt(sum(x * x for x in vec)) < 1e-9:
        return "invalid"
    return None


def norm(vec) -> float:
    return math.sqrt(sum(x * x for x in vec))


def outliers(norms: list[float]) -> set[int]:
    """Indexes whose L2 norm is less than half or more than double the batch median (needs >= 10 vectors)."""
    if len(norms) < 10:
        return set()
    med = statistics.median(norms)
    if med <= 0:
        return set()
    return {i for i, n in enumerate(norms) if n < 0.5 * med or n > 2.0 * med}


def fingerprint(vec) -> str:
    return hashlib.sha1(",".join(f"{x:.4f}" for x in vec).encode()).hexdigest()[:16]


async def run(ctx: PhaseCtx) -> None:
    if not ctx.state.get("scan_done"):
        await _scan(ctx)
        ctx.state["scan_done"] = True
        await ctx.checkpoint()
    _semantic_drift_pre(ctx)
    await _semantic_drift(ctx)
    if not ctx.state.get("canary_done"):
        await _canary(ctx)
        ctx.state["canary_done"] = True
        await ctx.checkpoint()


async def _scan(ctx: PhaseCtx) -> None:
    cfg, store, emb, tenant = ctx.cfg, ctx.deps.store, ctx.deps.embedder, ctx.tenant
    saved = await store.get_card_state(tenant, *CURSOR_KEY) or {}
    cursor = ctx.state.get("cursor", saved.get("cursor"))
    seen_fp: dict[str, list] = ctx.shared.setdefault("_fp", {})
    budget = max(0, cfg.embed_scan_per_night - int(ctx.state.get("scanned", 0)))
    reembed_left = 0 if ctx.dry_run else max(0, cfg.reembed_per_night - int(ctx.state.get("reembedded", 0)))
    problems: dict[str, list] = {"missing": [], "bad_dim": [], "invalid": [], "outlier": [], "model_mismatch": []}
    dups_identical, dups_collapsed = [], []
    wrapped = False
    while budget > 0:
        page = await store.scan_cards(tenant, tuple(cursor) if cursor else None, min(cfg.batch_size, budget),
                                      with_embedding=True, first_chunk_only=False)
        if not page:
            cursor, wrapped = None, True
            break
        cursor = [page[-1].source_type, page[-1].source_id, page[-1].chunk_no]
        budget -= len(page)
        ctx.state["scanned"] = int(ctx.state.get("scanned", 0)) + len(page)
        good = [c for c in page if vector_problem(c.embedding, emb.dim) is None]
        odd = outliers([norm(c.embedding) for c in good])
        odd_ids = {id(good[i]) for i in odd}
        batch_fix = []
        for c in page:
            prob = vector_problem(c.embedding, emb.dim)
            key = (c.source_type, c.source_id, c.chunk_no)
            if prob:
                problems[prob].append(key)
                if prob != "bad_dim":
                    batch_fix.append(c)
                continue
            if id(c) in odd_ids:
                problems["outlier"].append(key)
                batch_fix.append(c)
            if c.embedding_model != emb.model:
                problems["model_mismatch"].append(key)
                batch_fix.append(c)
            fp = fingerprint(c.embedding)
            other = seen_fp.get(fp)
            if other and tuple(other[:2]) != key[:2]:
                (dups_identical if other[2] == c.content_hash else dups_collapsed).append([list(other[:2]), list(key[:2])])
            else:
                seen_fp[fp] = [c.source_type, c.source_id, c.content_hash]
        if batch_fix and reembed_left > 0:
            seen_ids, uniq = set(), []
            for c in batch_fix:
                if (c.source_type, c.source_id, c.chunk_no) not in seen_ids:
                    seen_ids.add((c.source_type, c.source_id, c.chunk_no))
                    uniq.append(c)
            done = await _reembed(ctx, uniq[:reembed_left])
            reembed_left -= done
            ctx.state["reembedded"] = int(ctx.state.get("reembedded", 0)) + done
        ctx.state["cursor"] = cursor
        await ctx.pause()
    ctx.state["cursor"] = cursor
    if not ctx.dry_run:
        await store.put_card_state(tenant, *CURSOR_KEY, {"cursor": cursor, "at": ctx.now.isoformat()})
    ctx.counts.update({"scanned": int(ctx.state.get("scanned", 0)), "reembedded": int(ctx.state.get("reembedded", 0)),
                       "scan_wrapped": int(wrapped), **{f"vec_{k}": len(v) for k, v in problems.items()},
                       "vec_dup_identical": len(dups_identical), "vec_dup_collapsed": len(dups_collapsed)})
    scanned = max(1, int(ctx.state.get("scanned", 0)))
    bad = len(problems["missing"]) + len(problems["invalid"]) + len(problems["outlier"])
    if problems["bad_dim"]:
        await ctx.finding(type="embedding_dimension_mismatch", severity="high",
                          title=f"{len(problems['bad_dim'])} vector(s) do not have the configured {emb.dim} dimensions",
                          detail={"examples": [list(k) for k in problems["bad_dim"][:5]], "model": emb.model,
                                  "fix": "the pgvector column has a fixed dimension: drop the derived table and reindex with the new model"},
                          dedupe_key="embedding_dimension_mismatch", action={"kind": "none"})
    if bad:
        await ctx.finding(type="embedding_invalid", severity="high" if bad / scanned > 0.01 else "medium",
                          title=f"{bad} invalid vector(s) among {scanned} scanned (missing/NaN/zero/outlier norm)",
                          detail={k: len(problems[k]) for k in ("missing", "invalid", "outlier")} | {"reembedded_tonight": int(ctx.state.get("reembedded", 0)),
                                  "examples": [list(k) for k in (problems["missing"] + problems["invalid"] + problems["outlier"])[:5]]},
                          dedupe_key="embedding_invalid", auto_applied=bool(ctx.state.get("reembedded")), action={"kind": "none"})
    if problems["model_mismatch"]:
        await ctx.finding(type="embedding_model_changed", severity="medium",
                          title=f"{len(problems['model_mismatch'])} chunk(s) were embedded by a different model than '{emb.model}'",
                          detail={"reembedded_tonight": int(ctx.state.get("reembedded", 0)), "limit_per_night": cfg.reembed_per_night,
                                  "examples": [list(k) for k in problems["model_mismatch"][:5]]},
                          dedupe_key="embedding_model_changed", auto_applied=bool(ctx.state.get("reembedded")), action={"kind": "none"})
    if dups_collapsed:
        await ctx.finding(type="embedding_collapse", severity="medium",
                          title=f"{len(dups_collapsed)} pair(s) of cards with different text share an identical vector (embedding collapse)",
                          detail={"examples": dups_collapsed[:5]}, dedupe_key="embedding_collapse", action={"kind": "none"})
    if dups_identical:
        await ctx.finding(type="duplicate_vectors", severity="info", title=f"{len(dups_identical)} pair(s) of cards have identical text and vectors",
                          detail={"examples": dups_identical[:5]}, dedupe_key="duplicate_vectors", action={"kind": "none"})


async def _reembed(ctx: PhaseCtx, chunks: list) -> int:
    emb, store, tenant = ctx.deps.embedder, ctx.deps.store, ctx.tenant
    done = 0
    for i in range(0, len(chunks), 16):
        batch = chunks[i:i + 16]
        try:
            vecs = await emb.embed_documents([c.markdown for c in batch])
        except EmbeddingError as exc:
            ctx.error("re-embed", exc)
            ctx.note("embedding service unavailable: remaining re-embeds postponed")
            return done
        for c, v in zip(batch, vecs):
            if vector_problem(v, emb.dim) is not None:
                ctx.inc("reembed_still_invalid")
                continue
            if await store.set_embedding(ctx.tenant, c.source_type, c.source_id, c.chunk_no, v, emb.model,
                                         content_hash(stable_text(c.markdown), emb.model)):
                done += 1
        if ctx.cfg.sleep_s > 0:
            await ctx.deps.sleep(ctx.cfg.sleep_s)
        ctx.check_kill()
    return done


def _semantic_drift_pre(ctx: PhaseCtx) -> None:
    ctx.shared.setdefault("_refreshed", [])


async def _semantic_drift(ctx: PhaseCtx) -> None:
    dists = []
    for st, sid, old in ctx.shared.get("_refreshed", []):
        chunks = await ctx.deps.store.get_chunks(ctx.tenant, st, sid)
        if not chunks or not chunks[0].embedding or len(chunks[0].embedding) != len(old):
            continue
        d = round(1.0 - cosine(old, chunks[0].embedding), 4)
        dists.append(d)
        if d > ctx.cfg.semantic_drift:
            await ctx.finding(type="semantic_drift", severity="medium" if d > 0.5 else "low", source_type=st, source_id=sid,
                              title=f"Card '{chunks[0].title[:80]}' changed a lot in meaning (distance {d:.2f})",
                              detail={"cosine_distance": d, "threshold": ctx.cfg.semantic_drift}, action={"kind": "none"})
            ctx.inc("semantic_drift")
    ctx.counts["refreshed_compared"] = len(dists)
    if dists:
        ctx.counts["semantic_drift_max"] = max(dists)
        ctx.counts["semantic_drift_mean"] = round(sum(dists) / len(dists), 4)
    ctx.shared["_refreshed"] = []


def clean_title(t: str) -> str:
    return _PART.sub("", t).strip()


async def _canary(ctx: PhaseCtx) -> None:
    cfg, deps, tenant = ctx.cfg, ctx.deps, ctx.tenant
    if cfg.canary_n <= 0:
        return
    cands = await deps.store.top_cards(tenant, cfg.canary_n * 3)
    titles: dict[str, int] = {}
    for c in cands:
        titles[clean_title(c.title).lower()] = titles.get(clean_title(c.title).lower(), 0) + 1
    probes = [c for c in cands if titles[clean_title(c.title).lower()] == 1 and len(clean_title(c.title)) >= 6
              and c.valid_to is None][:cfg.canary_n]
    if not probes:
        ctx.note("no canary probes: no indexed card has a unique, long enough title")
        ctx.shared["canary"] = {"n": 0, "recall_at_3": None, "misses": []}
        return
    retr = KnowledgeRetriever(deps.store.kstore, deps.embedder, now=deps.now)
    scope = AccessScope(tenant_id=tenant, is_admin=True)
    hits, misses, degraded = 0, [], False
    for c in probes:
        try:
            res = await retr.search(clean_title(c.title), scope, Filters(), k=3)
        except EmbeddingError as exc:
            ctx.error("canary probe", exc)
            ctx.note("embedding service unavailable: canary recall not measured tonight")
            ctx.shared["canary"] = {"n": 0, "recall_at_3": None, "misses": [], "skipped": True}
            return
        degraded = degraded or bool(res.degraded)
        top = [(h.chunk.source_type, h.chunk.source_id) for h in res.hits[:3]]
        if (c.source_type, c.source_id) in top:
            hits += 1
        else:
            misses.append({"source_type": c.source_type, "source_id": c.source_id, "title": clean_title(c.title)[:80]})
        if cfg.sleep_s > 0:
            await deps.sleep(min(cfg.sleep_s, 0.2))
    n = len(probes)
    recall = round(hits / n, 4)
    prev = await _previous_recall(ctx)
    ctx.shared["canary"] = {"n": n, "hits": hits, "recall_at_3": recall, "misses": misses[:5], "previous": prev, "degraded": degraded}
    ctx.counts.update({"canary_n": n, "canary_hits": hits, "canary_recall_at_3": recall})
    dropped = prev is not None and (prev - recall) >= cfg.canary_alert_drop
    if n >= 5 and (dropped or recall < cfg.canary_recall_floor):
        sev = "critical" if recall < 0.3 else "high"
        await ctx.finding(type="canary_recall_drop", severity=sev,
                          title=f"Retrieval self-test: only {hits}/{n} important cards found themselves in the top 3 (recall {recall:.0%}"
                                + (f", was {prev:.0%}" if prev is not None else "") + ")",
                          detail={"recall_at_3": recall, "previous": prev, "floor": cfg.canary_recall_floor, "misses": misses[:5],
                                  "text_only_fallback": degraded}, dedupe_key="canary_recall_drop", action={"kind": "none"})


async def _previous_recall(ctx: PhaseCtx):
    for r in await ctx.deps.store.list_runs(ctx.tenant, 10, include_dry=False):
        if r["id"] == ctx.run["id"]:
            continue
        c = (r.get("report") or {}).get("canary") or {}
        if c.get("recall_at_3") is not None:
            return float(c["recall_at_3"])
    return None
