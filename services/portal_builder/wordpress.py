"""Tenant-owned WordPress destinations and durable publication attempts.

Remote IO happens after committing the immutable job. Ambiguous writes block further
writes until status reconciliation; retries use the same remote export identity.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from services.common import secretbox
from services.common.auth import AuthContext, get_auth_context
from services.common.db import Base, session_scope
from services.common.rate_limiter import RateLimiter
from services.portal_builder.access import require_tier
from services.portal_builder.wordpress_client import ABILITIES, WordPressClient, WordPressError, site_url
from services.portal_builder.wordpress_export import ExportError, export_page

router = APIRouter(prefix="/api/v1/portal/wordpress", tags=["WordPress"])
limiter = RateLimiter(max_requests=30, window_seconds=60)


def now():
    return datetime.now(timezone.utc)


class WordPressConnection(Base):
    __tablename__ = "portal_wordpress_connections"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    site_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    username: Mapped[str] = mapped_column(String(200), nullable=False)
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    site_name: Mapped[str] = mapped_column(String(300), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    abilities: Mapped[list] = mapped_column(JSONB, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (Index("ux_portal_wp_site", "tenant_id", "site_url", unique=True),)


class WordPressPageLink(Base):
    __tablename__ = "portal_wordpress_page_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_pages.id", ondelete="CASCADE"), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_wordpress_connections.id"), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    pending_job: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    __table_args__ = (Index("ux_portal_wp_page", "tenant_id", "page_id", "connection_id", unique=True),)


class WordPressJob(Base):
    __tablename__ = "portal_wordpress_publication_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portal_wordpress_page_links.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    exported_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_url: str = Field(min_length=1, max_length=1000)
    username: str = Field(min_length=1, max_length=200, pattern=r"^[^:\r\n]+$")
    application_password: SecretStr = Field(min_length=1, max_length=200)


class PublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exported_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def public_connection(c):
    return {"id": str(c.id), "site_url": c.site_url, "site_name": c.site_name,
            "username": c.username, "active": c.active, "abilities": c.abilities,
            "checked_at": c.checked_at.isoformat(), "credentials_configured": bool(c.password_enc)}


async def connection(db, cid, ctx, *, active=True):
    c = await db.scalar(select(WordPressConnection).where(WordPressConnection.id == cid,
                       WordPressConnection.tenant_id == ctx.tenant_id).with_for_update())
    if c is None:
        raise HTTPException(404, "WordPress connection not found")
    if active and not c.active:
        raise HTTPException(409, "Reconnect this WordPress site before using it")
    return c


def client_for(c):
    try:
        return WordPressClient(c.site_url, c.username, secretbox.decrypt(c.password_enc))
    except secretbox.SecretsUnavailable as exc:
        raise HTTPException(503, "WordPress credentials cannot be decrypted; check SECRETS_ENCRYPTION_KEY") from exc


async def check_site(url, username, password):
    async with WordPressClient(url, username, password) as client:
        abilities = await client.discover()
        if ABILITIES - set(abilities):
            raise WordPressError("Install and activate the OmniDome companion plugin; required abilities are missing.", 422)
        info = await client.execute("omnidome/site-info", {})
        if info.get("integration_version") != 1:
            raise WordPressError("The WordPress companion plugin has an incompatible integration version", 422)
        return abilities, str(info.get("site_name") or url)[:300]


@router.get("/connections")
async def list_connections(ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as db:
        rows = (await db.scalars(select(WordPressConnection).where(WordPressConnection.tenant_id == ctx.tenant_id)
                               .order_by(WordPressConnection.checked_at.desc()))).all()
        return {"items": [public_connection(c) for c in rows]}


@router.post("/connections", status_code=201)
async def connect(body: ConnectInput, ctx: AuthContext = Depends(require_tier("manager"))):
    limiter.check_key(str(ctx.user_id))
    try:
        encrypted = secretbox.encrypt(body.application_password.get_secret_value())
        url = await site_url(body.site_url)
        abilities, name = await check_site(url, body.username, body.application_password.get_secret_value())
    except secretbox.SecretsUnavailable as exc:
        raise HTTPException(503, "Configure SECRETS_ENCRYPTION_KEY before connecting WordPress") from exc
    except WordPressError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    async with session_scope() as db:
        row = await db.scalar(select(WordPressConnection).where(WordPressConnection.tenant_id == ctx.tenant_id,
                              WordPressConnection.site_url == url).with_for_update())
        if row:
            pending = await db.scalar(select(WordPressPageLink.id).where(WordPressPageLink.connection_id == row.id,
                                      WordPressPageLink.pending_job.is_not(None)))
            if pending:
                raise HTTPException(409, "Refresh pending publication status before replacing credentials")
            if row.username != body.username:
                raise HTTPException(409, "Use the original integration username to preserve WordPress page ownership")
            row.password_enc, row.abilities, row.site_name, row.active, row.checked_at = encrypted, abilities, name, True, now()
        else:
            row = WordPressConnection(tenant_id=ctx.tenant_id, site_url=url, username=body.username,
                                     password_enc=encrypted, site_name=name, abilities=abilities, checked_at=now(), active=True)
            db.add(row)
        try:
            await db.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "This site was connected by another request. Reload connected sites.") from exc
        return public_connection(row)


@router.post("/connections/{cid}/test")
async def test_connection(cid: uuid.UUID, ctx: AuthContext = Depends(require_tier("manager"))):
    limiter.check_key(str(ctx.user_id))
    async with session_scope() as db:
        c = await connection(db, cid, ctx)
        client = client_for(c)
    try:
        async with client:
            abilities = await client.discover()
            if ABILITIES - set(abilities):
                raise WordPressError("Required abilities are missing. Check the companion plugin.", 422)
            info = await client.execute("omnidome/site-info", {})
            if info.get("integration_version") != 1:
                raise WordPressError("Incompatible companion plugin", 422)
    except WordPressError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    async with session_scope() as db:
        c = await connection(db, cid, ctx)
        c.checked_at, c.abilities = now(), abilities
        await db.flush()
        return public_connection(c)


@router.delete("/connections/{cid}")
async def disconnect(cid: uuid.UUID, ctx: AuthContext = Depends(require_tier("manager"))):
    async with session_scope() as db:
        c = await connection(db, cid, ctx, active=False)
        pending = await db.scalar(select(WordPressPageLink.id).where(WordPressPageLink.connection_id == cid,
                                  WordPressPageLink.pending_job.is_not(None)))
        if pending:
            raise HTTPException(409, "Refresh pending publication status before disconnecting")
        c.active, c.password_enc = False, ""
        return {"status": "disconnected"}


def link_id(ctx, cid, pid):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"omnidome:wordpress:{ctx.tenant_id}:{cid}:{pid}")


async def page_and_link(db, cid, pid, ctx, *, create=False):
    from services.portal_builder.main import _get_page
    page = await _get_page(db, pid, ctx.tenant_id, lock=True)
    lid = link_id(ctx, cid, pid)
    link = await db.scalar(select(WordPressPageLink).where(WordPressPageLink.id == lid,
                           WordPressPageLink.tenant_id == ctx.tenant_id).with_for_update())
    if not link and create:
        link = WordPressPageLink(id=lid, tenant_id=ctx.tenant_id, page_id=pid, connection_id=cid, result={})
        db.add(link)
        await db.flush()
    return page, link


def publication_view(link, page, job=None):
    try:
        current_hash = export_page(page)["exported_hash"]
    except ExportError:
        current_hash = None
    result = dict(link.result) if link else {"status": "not_exported"}
    if job:
        result.update(status=job.status, error=job.error, job_id=str(job.id))
    result["local_changes"] = bool(link and current_hash != result.get("exported_hash"))
    result["current_hash"] = current_hash
    return result


@router.get("/connections/{cid}/pages/{pid}")
async def get_publication(cid: uuid.UUID, pid: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as db:
        await connection(db, cid, ctx, active=False)
        page, link = await page_and_link(db, cid, pid, ctx)
        job = await db.get(WordPressJob, link.pending_job) if link and link.pending_job else None
        return publication_view(link, page, job)


def validate_remote(result, url):
    if not isinstance(result, dict) or result.get("status") not in {"not_exported", "draft_exported", "published", "external_changes"}:
        raise WordPressError("Invalid WordPress publication status")
    for key in ("exported_hash", "published_hash"):
        value = result.get(key)
        if value is not None and (not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
            raise WordPressError("Invalid WordPress export identity")
    # Never expose arbitrary protocol-supplied links to the user.
    for field in ("preview_url", "live_url"):
        value = result.get(field)
        if value:
            if not isinstance(value, str) or len(value) > 2000:
                raise WordPressError("Invalid WordPress publication URL")
            p, origin = urlsplit(value), urlsplit(url)
            if p.scheme != "https" or p.netloc.lower() != origin.netloc.lower() or p.username or p.password:
                raise WordPressError("WordPress returned a URL outside the connected site")
    return {k: result.get(k) for k in ("status", "exported_hash", "published_hash", "preview_url", "live_url", "remote_id")}


async def perform(cid, pid, ctx, operation, approved_hash=None):
    limiter.check_key(str(ctx.user_id))
    async with session_scope() as db:
        c = await connection(db, cid, ctx)
        client, url = client_for(c), c.site_url
        page, link = await page_and_link(db, cid, pid, ctx, create=True)
        try:
            payload = export_page(page)
        except (ExportError, ValueError, TypeError) as exc:
            await client.http.aclose()
            raise HTTPException(422, str(exc)) from exc
        digest = payload["exported_hash"]
        if link.pending_job:
            await client.http.aclose()
            raise HTTPException(409, "Refresh WordPress status before starting another operation")
        if operation == "publish" and (approved_hash != digest or link.result.get("exported_hash") != digest):
            await client.http.aclose()
            raise HTTPException(409, "Export and review the current WordPress draft before publishing")
        jid = uuid.uuid5(link.id, operation + ":" + digest)
        job = await db.get(WordPressJob, jid)
        if not job:
            job = WordPressJob(id=jid, tenant_id=ctx.tenant_id, link_id=link.id, actor_id=ctx.user_id,
                               operation=operation, exported_hash=digest, payload=payload, status="running")
            db.add(job)
        else:
            job.status, job.error, job.actor_id, job.completed_at = "running", None, ctx.user_id, None
            job.created_at = now()
        link.pending_job = jid
    # Immutable job is committed before any remote mutation.
    error = None
    try:
        async with client:
            remote = await client.execute("omnidome/upsert-page-draft" if operation == "export" else "omnidome/publish-page",
                {"external_id": str(link.id), **payload} if operation == "export" else
                {"external_id": str(link.id), "exported_hash": digest})
            result = validate_remote(remote, url)
            expected = "draft_exported" if operation == "export" else "published"
            # Export of an identical already-published version is also a confirmed success.
            if result.get("exported_hash") != digest or result["status"] not in ({expected, "published"} if operation == "export" else {expected}):
                raise WordPressError("WordPress did not confirm the exported version")
    except WordPressError as exc:
        error = exc
    async with session_scope() as db:
        page, link = await page_and_link(db, cid, pid, ctx)
        job = await db.get(WordPressJob, jid)
        if error:
            job.status = "uncertain" if error.status >= 500 else "failed"
            job.error = str(error)
            if job.status == "failed":
                link.pending_job = None
        else:
            link.result = {**result, "warnings": payload["warnings"]}
            link.pending_job = None
            job.status, job.completed_at = "succeeded", now()
        return publication_view(link, page, job if error else None)


@router.post("/connections/{cid}/pages/{pid}/export")
async def export_draft(cid: uuid.UUID, pid: uuid.UUID, ctx: AuthContext = Depends(require_tier("write"))):
    return await perform(cid, pid, ctx, "export")


@router.post("/connections/{cid}/pages/{pid}/publish")
async def publish(cid: uuid.UUID, pid: uuid.UUID, body: PublishInput, ctx: AuthContext = Depends(require_tier("manager"))):
    return await perform(cid, pid, ctx, "publish", body.exported_hash)


@router.post("/connections/{cid}/pages/{pid}/refresh")
async def refresh(cid: uuid.UUID, pid: uuid.UUID, ctx: AuthContext = Depends(require_tier("write"))):
    limiter.check_key(str(ctx.user_id))
    async with session_scope() as db:
        c = await connection(db, cid, ctx)
        page, link = await page_and_link(db, cid, pid, ctx)
        if not link:
            return publication_view(None, page)
        client, url, lid, pending = client_for(c), c.site_url, link.id, link.pending_job
    try:
        async with client:
            remote = await client.execute("omnidome/get-publication-status", {"external_id": str(lid)})
            result = validate_remote(remote, url)
    except WordPressError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    async with session_scope() as db:
        page, link = await page_and_link(db, cid, pid, ctx)
        if link.pending_job != pending:
            raise HTTPException(409, "Publication changed while checking status; refresh again")
        if pending:
            job = await db.get(WordPressJob, pending)
            # A live in-flight HTTP request may still finish: do not unlock it early.
            started = job.created_at.replace(tzinfo=timezone.utc) if job.created_at.tzinfo is None else job.created_at
            if job.status == "running" and (now() - started).total_seconds() < 120:
                return publication_view(link, page, job)
            key = "published_hash" if job.operation == "publish" else "exported_hash"
            confirmed = result.get(key) == job.exported_hash
            job.status, job.completed_at = ("succeeded" if confirmed else "failed"), now()
            job.error = None if confirmed else "WordPress did not apply this version. You can retry after reviewing the remote page."
            link.pending_job = None
            warnings = job.payload.get("warnings", [])
        else:
            warnings = link.result.get("warnings", [])
        link.result = {**result, "warnings": warnings}
        return publication_view(link, page)
