"""Home Assistant reference library: official integration docs and community answers, stored as text for the knowledge base.

Deterministic sources first, Firecrawl only as a fallback:
  * Integration docs: the markdown source of home-assistant.io on GitHub (no scraping, stable URLs).
  * Community: the Discourse JSON API of community.home-assistant.io (search, category listing, topic).
  * Firecrawl: used for an integration page only when the markdown source is missing.

The library is platform-wide (not tenant data); the tenant_memory `ha_reference` source turns it into cards.
Licence note: the home-assistant.io docs are CC BY-NC-SA 4.0 and community posts are user content. We keep the
source URL and licence with every document so answers can cite and link back instead of republishing.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
from html.parser import HTMLParser
from typing import Any, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger("iot.ha_reference")

DOCS_RAW = "https://raw.githubusercontent.com/home-assistant/home-assistant.io/current/source/_integrations/{domain}.markdown"
DOCS_PAGE = "https://www.home-assistant.io/integrations/{domain}/"
COMMUNITY = "https://community.home-assistant.io"
USER_AGENT = "OmniDomeKnowledge/1.0 (+reference library; contact: platform admin)"
DOC_LICENSE = "CC BY-NC-SA 4.0 (home-assistant.io)"
COMMUNITY_LICENSE = "Home Assistant Community user content"
MAX_BODY = 24000
MAX_TOPIC_BODY = 9000
POLITE_DELAY_S = 1.0

DDL = (
    """CREATE TABLE IF NOT EXISTS ha_reference_docs (
        doc_key text PRIMARY KEY, kind text NOT NULL, title text NOT NULL, url text NOT NULL,
        integration_id text, body text NOT NULL, content_hash text NOT NULL, license text NOT NULL,
        extra jsonb NOT NULL DEFAULT '{}'::jsonb, fetched_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_ha_reference_docs_integration ON ha_reference_docs (integration_id)",
)


async def ensure_table(session) -> None:
    for statement in DDL:
        await session.execute(text(statement))


# ── Text clean-up ─────────────────────────────────────────────────────────────

class _CookedText(HTMLParser):
    """Discourse `cooked` HTML to plain text, keeping code blocks fenced and list items bulleted."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._pre = 0

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self._pre += 1
            self.out.append("\n```\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("p", "br", "h1", "h2", "h3", "h4", "blockquote", "div"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag == "pre" and self._pre:
            self._pre -= 1
            self.out.append("\n```\n")
        elif tag in ("p", "h1", "h2", "h3", "h4", "blockquote"):
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data)


def cooked_to_text(cooked: str) -> str:
    parser = _CookedText()
    parser.feed(cooked or "")
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.out)).strip()


_LIQUID = re.compile(r"\{%-?.*?-?%\}", re.S)
_LIQUID_VAR = re.compile(r"\{\{.*?\}\}", re.S)


def clean_docs_markdown(raw: str) -> tuple[dict, str]:
    """Split YAML-ish front matter from the body and drop Jekyll/Liquid tags that mean nothing outside the site."""
    meta: dict[str, Any] = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            front, body = raw[3:end], raw[end + 4:]
            key = None
            for line in front.splitlines():
                m = re.match(r"^([a-z_]+):\s*(.*)$", line)
                if m:
                    key = m.group(1)
                    value = m.group(2).strip().strip("'\"")
                    meta[key] = value if value else []
                elif key and line.strip().startswith("- ") and isinstance(meta.get(key), list):
                    meta[key].append(line.strip()[2:].strip().strip("'\""))
    body = _LIQUID.sub("", body)
    body = _LIQUID_VAR.sub("", body)
    return meta, re.sub(r"\n{3,}", "\n\n", body).strip()


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


# ── Fetching ──────────────────────────────────────────────────────────────────

def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})


async def fetch_integration(domain: str, client: Optional[httpx.AsyncClient] = None) -> Optional[dict]:
    """Official docs for one integration domain (for example `imou`, `zha`). None when it has no page."""
    if not re.fullmatch(r"[a-z0-9_]{1,64}", domain or ""):
        raise ValueError("Invalid integration id")
    own = client is None
    client = client or _client()
    try:
        resp = await client.get(DOCS_RAW.format(domain=domain))
        if resp.status_code == 200:
            meta, body = clean_docs_markdown(resp.text)
            source = "github"
        else:
            body, meta, source = await _firecrawl_page(DOCS_PAGE.format(domain=domain)), {}, "firecrawl"
            if not body:
                return None
    finally:
        if own:
            await client.aclose()
    title = meta.get("title") or domain
    facts = [f"Integration: {title} (domain `{domain}`)"]
    for key, label in (("description", "Summary"), ("ha_category", "Categories"), ("ha_iot_class", "IoT class"),
                       ("ha_release", "Available since"), ("ha_config_flow", "UI setup (config flow)"),
                       ("ha_integration_type", "Type")):
        value = meta.get(key)
        if value:
            facts.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    text_body = "\n".join(facts) + "\n\n" + body
    return {"doc_key": f"integration:{domain}", "kind": "integration", "title": f"Home Assistant: {title}",
            "url": DOCS_PAGE.format(domain=domain), "integration_id": domain, "body": text_body[:MAX_BODY],
            "license": DOC_LICENSE, "extra": {"source": source, "meta": {k: v for k, v in meta.items() if k.startswith("ha_")}}}


async def _firecrawl_page(url: str) -> str:
    try:
        from services.common.firecrawl import firecrawl
        result = await firecrawl.scrape(url)
        if isinstance(result, dict):
            result = result.get("markdown") or result.get("content") or ""
        return str(result or "")[:MAX_BODY]
    except Exception as exc:  # noqa: BLE001 - fallback only; keyless limits and outages must not break a refresh
        logger.info("Firecrawl fallback unavailable for %s: %s", url, type(exc).__name__)
        return ""


def _topic_doc(data: dict) -> Optional[dict]:
    """Condense a Discourse topic: question, accepted answer if any, then the first replies. Authors are left out."""
    posts = (data.get("post_stream") or {}).get("posts") or []
    if not posts:
        return None
    accepted_id = (data.get("accepted_answer") or {}).get("post_number")
    chosen = [posts[0]] + [p for p in posts[1:] if p.get("post_number") == accepted_id]
    chosen += [p for p in posts[1:6] if p not in chosen]
    parts, size = [], 0
    for post in chosen:
        label = "Question" if post is posts[0] else ("Accepted answer" if post.get("post_number") == accepted_id else "Reply")
        body = cooked_to_text(post.get("cooked", ""))
        if not body:
            continue
        piece = f"## {label}\n{body}"
        if size + len(piece) > MAX_TOPIC_BODY:
            piece = piece[:max(0, MAX_TOPIC_BODY - size)]
        parts.append(piece)
        size += len(piece)
        if size >= MAX_TOPIC_BODY:
            break
    if not parts:
        return None
    topic_id = data["id"]
    tags = [t.get("name") if isinstance(t, dict) else str(t) for t in (data.get("tags") or [])]
    tags = [t for t in tags if t]
    header = f"Community topic: {data.get('title', '')}" + (f"\nTags: {', '.join(tags)}" if tags else "")
    header += "\nResolved: yes" if accepted_id else "\nResolved: not marked"
    return {"doc_key": f"community:{topic_id}", "kind": "community", "title": f"HA Community: {data.get('title', '')}",
            "url": f"{COMMUNITY}/t/{data.get('slug', 'topic')}/{topic_id}", "integration_id": None,
            "body": header + "\n\n" + "\n\n".join(parts), "license": COMMUNITY_LICENSE,
            "extra": {"accepted": bool(accepted_id), "posts": data.get("posts_count"), "category_id": data.get("category_id")}}


async def fetch_topic(topic_id: int, client: httpx.AsyncClient) -> Optional[dict]:
    resp = await client.get(f"{COMMUNITY}/t/{int(topic_id)}.json")
    if resp.status_code != 200:
        return None
    return _topic_doc(resp.json())


async def search_topic_ids(query: str, client: httpx.AsyncClient, limit: int = 5) -> list[int]:
    resp = await client.get(f"{COMMUNITY}/search.json", params={"q": query[:200]})
    if resp.status_code != 200:
        return []
    ids: list[int] = []
    for topic in resp.json().get("topics", []):
        if topic.get("id") not in ids:
            ids.append(topic["id"])
    return ids[:limit]


async def category_topic_ids(slug: str, client: httpx.AsyncClient, pages: int = 1, solved_only: bool = True) -> list[int]:
    """Topics of a community category (for example `configuration`), newest first; solved ones when the plugin reports it."""
    ids: list[int] = []
    for page in range(max(1, min(pages, 5))):
        resp = await client.get(f"{COMMUNITY}/c/{slug}.json", params={"page": page})
        if resp.status_code != 200:
            break
        topics = (resp.json().get("topic_list") or {}).get("topics", [])
        if not topics:
            break
        ids += [t["id"] for t in topics if (t.get("has_accepted_answer") or not solved_only) and t.get("posts_count", 1) > 1]
        await asyncio.sleep(POLITE_DELAY_S)
    return ids


# ── Store ─────────────────────────────────────────────────────────────────────

async def upsert(session, doc: dict) -> str:
    """Insert or update a document. Returns `new`, `updated` or `unchanged` (identical content is left alone)."""
    digest = _hash(doc["title"], doc["body"])
    row = (await session.execute(text("SELECT content_hash FROM ha_reference_docs WHERE doc_key = :k"),
                                 {"k": doc["doc_key"]})).first()
    if row and row[0] == digest:
        await session.execute(text("UPDATE ha_reference_docs SET fetched_at = now() WHERE doc_key = :k"), {"k": doc["doc_key"]})
        return "unchanged"
    await session.execute(text(
        """INSERT INTO ha_reference_docs (doc_key, kind, title, url, integration_id, body, content_hash, license, extra, fetched_at)
           VALUES (:doc_key, :kind, :title, :url, :integration_id, :body, :h, :license, CAST(:extra AS jsonb), now())
           ON CONFLICT (doc_key) DO UPDATE SET title = :title, url = :url, body = :body, content_hash = :h,
             license = :license, extra = CAST(:extra AS jsonb), fetched_at = now()"""),
        {**{k: doc.get(k) for k in ("doc_key", "kind", "title", "url", "integration_id", "body", "license")},
         "h": digest, "extra": json.dumps(doc.get("extra") or {})})
    return "updated" if row else "new"


async def refresh(session, integrations: Optional[list[str]] = None, queries: Optional[list[str]] = None,
                  categories: Optional[list[str]] = None, per_query: int = 3, category_pages: int = 1) -> dict:
    """Fetch and store the requested documents. Each failure is counted, never raised, so one bad page cannot stop a refresh."""
    stats = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0, "missing": []}
    await ensure_table(session)
    async with _client() as client:
        for domain in integrations or []:
            try:
                doc = await fetch_integration(domain, client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("integration %s failed: %s", domain, type(exc).__name__)
                stats["failed"] += 1
                continue
            if doc is None:
                stats["missing"].append(domain)
                continue
            stats[await upsert(session, doc)] += 1
            await asyncio.sleep(0.2)
        topic_ids: list[int] = []
        try:
            for query in queries or []:
                topic_ids += await search_topic_ids(query, client, per_query)
                await asyncio.sleep(POLITE_DELAY_S)
            for slug in categories or []:
                topic_ids += await category_topic_ids(slug, client, category_pages)
        except httpx.HTTPError as exc:
            logger.warning("community listing failed: %s", type(exc).__name__)
            stats["failed"] += 1
        for topic_id in dict.fromkeys(topic_ids):
            try:
                doc = await fetch_topic(topic_id, client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("topic %s failed: %s", topic_id, type(exc).__name__)
                stats["failed"] += 1
                continue
            if doc:
                stats[await upsert(session, doc)] += 1
            await asyncio.sleep(POLITE_DELAY_S)
    return stats


async def lookup(session, query: str, limit: int = 5, live: bool = True) -> dict:
    """Answer a question from the stored library; when it holds little on the topic and `live` is set, fetch the best
    community topics now, store them (so the knowledge base gains them) and answer again."""
    await ensure_table(session)
    words = [w for w in re.findall(r"[a-z0-9_]{3,}", query.lower())][:8]
    rows: list[Any] = []

    async def search() -> list[Any]:
        if not words:
            return []
        conditions = " OR ".join(f"lower(title || ' ' || body) LIKE :w{i}" for i in range(len(words)))
        params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
        found = (await session.execute(text(
            f"SELECT doc_key, kind, title, url, left(body, 1500) AS snippet, license FROM ha_reference_docs WHERE {conditions} "
            "ORDER BY (kind = 'integration') DESC, fetched_at DESC LIMIT 40"), params)).mappings().all()
        scored = sorted(found, key=lambda r: -sum(w in (r["title"] + " " + r["snippet"]).lower() for w in words))
        return [dict(r) for r in scored[:limit]]

    rows = await search()
    fetched = False
    if live and len(rows) < 2:
        stats = await refresh(session, queries=[query], per_query=limit)
        fetched = bool(stats["new"] or stats["updated"])
        rows = await search()
    return {"query": query, "live_fetch": fetched, "results": rows}
