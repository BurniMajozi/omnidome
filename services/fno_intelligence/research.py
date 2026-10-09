"""A. Online research with citations.

POST /analytics/research -> Firecrawl search (markdown included) -> cap each page -> LLM synthesis ->
server-side validation: every claim must cite source ids that Firecrawl actually returned; claims
without a valid source are stripped, quotes must literally appear in the cited page and are short.
URLs only ever come from Firecrawl results, never from the model.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_current_tenant_id
from services.common.background_tasks import schedule_background
from services.fno_intelligence import analytics_common as ac
from services.fno_intelligence import database
from services.fno_intelligence.analytics_models import AiResearchRun

logger = logging.getLogger("fno_intelligence.research")
router = APIRouter(prefix="/research", tags=["Analytics: research"])

DEPTH = {  # search results requested, default sources used, chars of each page given to the model
    "quick": {"search_limit": 5, "sources": 3, "chars": 5000, "extra_scrapes": 1},
    "standard": {"search_limit": 8, "sources": 6, "chars": 8000, "extra_scrapes": 2},
    "deep": {"search_limit": 12, "sources": 10, "chars": 10000, "extra_scrapes": 3},
}
RECENCY_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}
MAX_QUOTE_WORDS = 25
MAX_CONCURRENT_RUNS = 3

_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_CITE = re.compile(r"\[(S\d{1,2})\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

SYSTEM = (
    "You are a careful research analyst for an internet service provider. Answer the question using ONLY "
    "the numbered sources provided. Every statement must be supported by at least one source and carry its "
    "id. If sources conflict or are thin, say so. Do not use outside knowledge for facts.\n" + ac.UNTRUSTED_RULES
)

TASK = (
    "Question: {question}\n\n"
    "Return one JSON object: {{\"summary\": string (3-6 sentences, every sentence ends with citation markers "
    "like [S1] or [S1][S3]), \"key_findings\": [{{\"claim\": string, \"source_ids\": [\"S1\"], "
    "\"quote\": optional string, a verbatim excerpt of at most {qw} words from the cited source}}], "
    "\"limitations\": [string]}}. Use only these source ids: {ids}. Do not include URLs."
)


class ResearchCreate(BaseModel):
    question: str = Field(..., min_length=8, max_length=500)
    depth: Literal["quick", "standard", "deep"] = "standard"
    max_sources: Optional[int] = Field(None, ge=1, le=15)
    country: str = Field("za", pattern=r"^[A-Za-z]{2}$")
    recency: Optional[Literal["day", "week", "month", "year"]] = None


# ── pure functions (unit tested) ──────────────────────────────────────────

def _strip_urls(s: str) -> str:
    return re.sub(r"\s{2,}", " ", _URL.sub("", s or "")).strip()


def _in_source(quote: str, text_: str) -> bool:
    return bool(quote) and ac.norm_ws(quote).lower() in ac.norm_ws(text_).lower()


def validate_report(raw: object, sources: list[dict], texts: dict[str, str]) -> dict:
    """Turn the model's JSON into a report where every claim is tied to a real source id.

    Claims without a valid source are removed (counted in `stripped_claims`); summary sentences
    without a valid citation marker are removed; quotes must literally occur in a cited source and
    be short. Nothing the model says about URLs is kept.
    """
    valid = {s["id"] for s in sources}
    raw = raw if isinstance(raw, dict) else {}
    stripped = 0

    findings = []
    for f in raw.get("key_findings") or []:
        if not isinstance(f, dict):
            stripped += 1
            continue
        claim = _strip_urls(str(f.get("claim") or ""))[:600]
        ids = [i for i in dict.fromkeys(str(x).strip().upper() for x in (f.get("source_ids") or [])
                                        if isinstance(x, (str, int))) if i in valid]
        if not claim or not ids:
            stripped += 1
            continue
        item: dict = {"claim": claim, "source_ids": ids}
        quote = f.get("quote")
        if isinstance(quote, str) and quote.strip():
            q = quote.strip().strip("\"'“”")
            if len(q.split()) <= MAX_QUOTE_WORDS:
                for sid in ids:
                    if _in_source(q, texts.get(sid, "")):
                        item["quote"] = {"text": q, "source_id": sid}
                        break
        findings.append(item)

    kept = []
    for sent in _SENTENCE.split(str(raw.get("summary") or "").strip()):
        sent = _strip_urls(sent)
        if not sent:
            continue
        marks = _CITE.findall(sent)
        good = [m for m in marks if m in valid]
        if not good:
            stripped += 1
            continue
        for m in set(marks) - set(good):
            sent = sent.replace(f"[{m}]", "")
        kept.append(sent.strip())
    summary = " ".join(kept)
    if not summary and findings:
        summary = " ".join(f"{f['claim']} " + "".join(f"[{i}]" for i in f["source_ids"]) for f in findings[:3])

    limits = [_strip_urls(str(x))[:300] for x in (raw.get("limitations") or []) if isinstance(x, str) and x.strip()][:6]
    if stripped:
        limits.append(f"{stripped} statement(s) from the model were removed because they cited no valid source.")
    cited = {i for f in findings for i in f["source_ids"]} | set(_CITE.findall(summary))
    return {"summary": summary, "key_findings": findings, "limitations": limits,
            "stripped_claims": stripped, "cited_source_ids": sorted(cited)}


def render_markdown(run: dict) -> str:
    rep = run.get("report") or {}
    lines = [f"# Research: {run['question']}", "",
             f"*Depth: {run['depth']} - generated {run.get('finished_at') or run.get('created_at')} - "
             "AI-generated from the sources below; check the sources before relying on it.*", ""]
    lines += ["## Summary", "", rep.get("summary") or "_No supported summary._", ""]
    if rep.get("key_findings"):
        lines += ["## Key findings", ""]
        for f in rep["key_findings"]:
            lines.append(f"- {f['claim']} " + "".join(f"[{i}]" for i in f["source_ids"]))
            if f.get("quote"):
                lines.append(f"  > \"{f['quote']['text']}\" ({f['quote']['source_id']})")
        lines.append("")
    if rep.get("limitations"):
        lines += ["## Limitations", ""] + [f"- {x}" for x in rep["limitations"]] + [""]
    lines += ["## Sources", ""]
    for s in run.get("sources") or []:
        lines.append(f"- [{s['id']}] {s.get('title') or s['domain']} - {s['url']} (fetched {s['fetched_at']})")
    return "\n".join(lines) + "\n"


# ── pipeline ──────────────────────────────────────────────────────────────

async def gather_sources(mf: ac.MeteredFirecrawl, params: dict) -> tuple[list[dict], dict[str, str]]:
    cfg = DEPTH[params["depth"]]
    want = min(params.get("max_sources") or cfg["sources"], 15)
    raw = await mf.search(params["question"], limit=max(cfg["search_limit"], want), country=params["country"],
                          tbs=RECENCY_TBS.get(params.get("recency") or ""))
    sources, texts, seen = [], {}, set()
    extra = cfg["extra_scrapes"]
    for it in ac.results_from_search(raw):
        if len(sources) >= want:
            break
        url = ac.result_url(it)
        if not url or url in seen:
            continue
        seen.add(url)
        text_ = ac.result_text(it)
        if len(text_.strip()) < 200 and extra > 0 and await ac.is_safe_to_fetch(url):
            extra -= 1
            try:
                text_ = ((await mf.scrape(url)).get("data") or {}).get("markdown") or ""
            except ac.CreditCapExceeded:
                raise
            except Exception as exc:  # one dead page must not sink the run
                logger.info("research scrape skipped %s: %s", url, exc)
                continue
        if len(text_.strip()) < 200:
            continue
        sid = f"S{len(sources) + 1}"
        texts[sid] = text_[: cfg["chars"]]
        snippet = ac.norm_ws(ac.clean_untrusted(str(it.get("description") or text_), 400))[:240]
        sources.append({"id": sid, "title": ac.result_title(it), "url": url, "domain": ac.domain_of(url),
                        "fetched_at": ac.now().isoformat(), "snippet": snippet})
    return sources, texts


async def synthesize(question: str, sources: list[dict], texts: dict[str, str], chars: int) -> tuple[dict, str]:
    blocks = "\n\n".join(ac.wrap_source(s["id"], s["url"], texts[s["id"]], chars) for s in sources)
    user = TASK.format(question=question, qw=MAX_QUOTE_WORDS, ids=", ".join(s["id"] for s in sources)) + "\n\n" + blocks
    res = await ac.llm_complete(SYSTEM, user, max_tokens=2500)
    if res is None:
        raise RuntimeError("No language model is available right now (check the OpenRouter key/models).")
    content, model = res
    parsed = ac.parse_json_loose(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("The model did not return a usable report.")
    return validate_report(parsed, sources, texts), model


async def run_pipeline(tenant_id: uuid.UUID, run_id: uuid.UUID, params: dict) -> dict:
    mf = ac.MeteredFirecrawl(tenant_id, "research", run_id)
    sources, texts = await gather_sources(mf, params)
    out = {"sources": sources, "credits": mf.spent, "report": None, "model": None}
    if not sources:
        out["report"] = {"summary": "", "key_findings": [], "stripped_claims": 0, "cited_source_ids": [],
                         "limitations": ["No readable web pages were found for this question."]}
        return out
    report, model = await synthesize(params["question"], sources, texts, DEPTH[params["depth"]]["chars"])
    report["limitations"].append("Based only on the pages listed under sources; paywalled or blocked pages are not covered.")
    out.update(report=report, model=model)
    return out


async def execute_research(tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """Background entry point: owns its DB sessions (never the request's)."""
    async with database.get_session_factory()() as db:
        run = await db.get(AiResearchRun, run_id)
        if run is None or run.tenant_id != tenant_id or run.status != "queued":
            return
        run.status, run.started_at = "running", ac.now()
        params = dict(run.params or {}, question=run.question, depth=run.depth)
        await db.commit()
    result, error, spent = None, None, 0
    try:
        result = await run_pipeline(tenant_id, run_id, params)
    except Exception as exc:
        error = ac.err_text(exc)
        logger.warning("research %s failed: %s", run_id, error)
    async with database.get_session_factory()() as db:
        run = await db.get(AiResearchRun, run_id)
        if run is None:
            return
        if result is not None:
            run.status, run.report, run.sources = "done", result["report"], result["sources"]
            run.credits_used, run.model_used = result["credits"], result["model"]
        else:
            run.status, run.error = "failed", error
        run.finished_at = ac.now()
        await db.commit()


async def sweep_stuck(db: AsyncSession, older_than_minutes: int = 30) -> int:
    from datetime import timedelta
    cutoff = ac.now() - timedelta(minutes=older_than_minutes)
    rows = (await db.execute(select(AiResearchRun).where(
        AiResearchRun.status.in_(("queued", "running")), AiResearchRun.created_at < cutoff))).scalars().all()
    for r in rows:
        r.status, r.error, r.finished_at = "failed", "Interrupted (service restarted) - run it again.", ac.now()
    return len(rows)


# ── routes ────────────────────────────────────────────────────────────────

def run_dict(r: AiResearchRun, *, full: bool = True) -> dict:
    d = {
        "id": str(r.id), "question": r.question, "depth": r.depth, "params": r.params or {},
        "status": r.status, "error": r.error, "credits_used": r.credits_used, "model_used": r.model_used,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "source_count": len(r.sources or []),
        "summary": (r.report or {}).get("summary") if r.report else None,
    }
    if full:
        d["report"], d["sources"] = r.report, r.sources
    return d


async def _get(db: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID) -> AiResearchRun:
    r = await db.get(AiResearchRun, run_id)
    if r is None or r.tenant_id != tenant_id:
        raise HTTPException(404, "Research run not found")
    return r


@router.post("", status_code=202)
async def create_research(body: ResearchCreate, auth: AuthContext = Depends(ac.require_analyst),
                          db: AsyncSession = Depends(database.get_session)):
    tenant_id = auth.tenant_id
    active = (await db.execute(select(func.count()).select_from(AiResearchRun).where(
        AiResearchRun.tenant_id == tenant_id, AiResearchRun.status.in_(("queued", "running"))))).scalar_one()
    if active >= MAX_CONCURRENT_RUNS:
        raise HTTPException(429, f"{MAX_CONCURRENT_RUNS} research runs are already in progress; wait for one to finish.")
    cfg = DEPTH[body.depth]
    await ac.check_headroom(tenant_id, ac.estimate_search(max(cfg["search_limit"], body.max_sources or 0)) + cfg["extra_scrapes"], db)
    run = AiResearchRun(tenant_id=tenant_id, created_by=auth.user_id, question=body.question.strip(),
                        depth=body.depth, status="queued",
                        params={"max_sources": body.max_sources, "country": body.country.lower(), "recency": body.recency})
    db.add(run)
    await db.flush()
    await db.commit()  # the background task reads it with its own session
    schedule_background(execute_research(tenant_id, run.id))
    return run_dict(run)


@router.get("")
async def list_research(status: Optional[Literal["queued", "running", "done", "failed"]] = None,
                        limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                        tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        _: AuthContext = Depends(ac.require_viewer),
                        db: AsyncSession = Depends(database.get_session)):
    q = select(AiResearchRun).where(AiResearchRun.tenant_id == tenant_id)
    if status:
        q = q.where(AiResearchRun.status == status)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(desc(AiResearchRun.created_at)).limit(limit).offset(offset))).scalars().all()
    return {"total": total, "limit": limit, "offset": offset, "items": [run_dict(r, full=False) for r in rows]}


@router.get("/{run_id}")
async def get_research(run_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    return run_dict(await _get(db, tenant_id, run_id))


@router.get("/{run_id}/export")
async def export_research(run_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                          _: AuthContext = Depends(ac.require_viewer), db: AsyncSession = Depends(database.get_session)):
    r = await _get(db, tenant_id, run_id)
    if r.status != "done":
        raise HTTPException(409, "Only finished research can be exported")
    return PlainTextResponse(render_markdown(run_dict(r)), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="research-{r.id}.md"'})


@router.delete("/{run_id}", status_code=204)
async def delete_research(run_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                          _: AuthContext = Depends(ac.require_admin), db: AsyncSession = Depends(database.get_session)):
    await db.delete(await _get(db, tenant_id, run_id))
