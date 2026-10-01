"""
Compliance Service — Document Upload & Understanding Routes
Handles file uploads, URL fetches, website crawls, OCR processing,
entity extraction, and document linking to compliance records.

Security: the tenant ALWAYS comes from the signed identity (a tenant_id sent in a
form or query string is ignored), uploaded files are stored under server-generated
names inside the upload root, and URLs go through the SSRF guard
(services.compliance.safe_fetch / services.common.url_safety).
"""
import json
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud, safe_fetch, upload_safety
from services.compliance.access import member_ctx, tenant_str, write_ctx
from services.compliance.database import ComplianceDocument, Contract, DocumentType

router = APIRouter(prefix="/documents", tags=["documents"])


def _architect():
    # Imported lazily: the architect pulls in heavy optional parsers (pymupdf, docx, ...).
    from services.compliance.document_architect import get_architect
    return get_architect()


async def _read_limited(file: UploadFile) -> bytes:
    limit = upload_safety.max_upload_bytes()
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, "File is too large")
    return content


# ── File Upload ────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type_hint: Optional[str] = Form(None),
    contract_id: Optional[int] = Form(None),
    process: bool = Form(True),
    ctx: AuthContext = Depends(write_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document and optionally process it through the understanding architect."""
    content = await _read_limited(file)
    try:
        ext = upload_safety.safe_extension(file.filename)
        upload_safety.check_content(ext, content)
    except upload_safety.UnsafeUpload as e:
        raise HTTPException(400, str(e))
    await crud.assert_owned(db, ctx, Contract, contract_id, "Contract")

    tenant = tenant_str(ctx)
    label = upload_safety.display_name(file.filename)
    architect = _architect()
    result = await architect.process_file(
        content=content,
        filename=f"upload{ext}",
        tenant_id=tenant,
        doc_type_hint=doc_type_hint,
        contract_id=contract_id,
    )

    doc_record = ComplianceDocument(
        title=label,
        document_type=_map_doc_type(result.document_type),
        file_path=result.stored_path or None,
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        contract_id=contract_id,
        ocr_text=result.cleaned_text[:50000] if result.cleaned_text else None,
        extracted_data=json.dumps({
            "entities": [{"label": e.label, "value": e.value, "confidence": e.confidence} for e in result.entities],
            "financials": [{"amount": f.amount, "currency": f.currency, "line_item": f.line_item} for f in result.financials],
            "links": [{"url": l.url, "type": l.link_type} for l in result.links],
            "dates": result.dates,
            "references": result.references,
        }, default=str) if result.entities or result.financials else None,
        financial_summary=json.dumps({
            "amounts": [{"amount": f.amount, "line_item": f.line_item, "context": f.context[:100]} for f in result.financials],
        }, default=str) if result.financials else None,
        tags=f"auto_classified:{result.document_type}" if result.document_type else None,
        uploaded_by=str(ctx.user_id),
        tenant_id=tenant,
    )
    db.add(doc_record)
    await db.commit()
    await db.refresh(doc_record)

    return {
        "status": "processed",
        "document_id": doc_record.id,
        "understanding": {
            "doc_id": result.doc_id,
            "title": result.title,
            "source": label,
            "format": result.doc_format,
            "document_type": result.document_type,
            "compliance_category": result.compliance_category,
            "confidence": result.confidence,
            "page_count": result.page_count,
            "file_size_bytes": result.file_size_bytes,
            "content_hash": result.content_hash,
            "entities": [{"label": e.label, "value": e.value, "confidence": e.confidence} for e in result.entities],
            "financials": [{"amount": f.amount, "currency": f.currency, "line_item": f.line_item, "context": f.context[:200]} for f in result.financials],
            "links": [{"url": l.url, "anchor": l.anchor_text, "type": l.link_type} for l in result.links],
            "dates": result.dates,
            "references": result.references,
            "markdown_preview": result.markdown[:1000] if result.markdown else "",
            "processing_time_ms": result.processing_time_ms,
            "errors": result.errors,
        },
    }


# ── URL Fetch ─────────────────────────────────────────────────────────

@router.post("/fetch-url")
async def fetch_url_document(
    url: str = Form(...),
    doc_type_hint: Optional[str] = Form(None),
    crawl: bool = Form(False),
    max_depth: int = Form(2, ge=0, le=3),
    ctx: AuthContext = Depends(write_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a public document from a URL and process it (SSRF-guarded)."""
    try:
        await safe_fetch.check_url(url)
    except safe_fetch.FetchRefused as e:
        raise HTTPException(400, f"URL refused: {e}")

    tenant = tenant_str(ctx)
    results = await _architect().process_url(
        url=url, tenant_id=tenant, crawl=crawl, max_depth=max_depth, doc_type_hint=doc_type_hint,
    )

    stored = []
    for result in results:
        if result.errors and not result.cleaned_text:
            stored.append({"source": result.source, "error": "; ".join(result.errors)})
            continue
        doc_record = ComplianceDocument(
            title=result.title or result.source,
            document_type=_map_doc_type(result.document_type),
            file_path=result.stored_path or None,
            file_size=result.file_size_bytes,
            mime_type="text/html" if result.doc_format == "html" else "application/octet-stream",
            ocr_text=result.cleaned_text[:50000] if result.cleaned_text else None,
            extracted_data=json.dumps({
                "entities": [{"label": e.label, "value": e.value} for e in result.entities],
                "links": [{"url": l.url, "type": l.link_type} for l in result.links],
                "references": result.references,
                "source_url": result.source,
            }, default=str) if result.entities else json.dumps({"source_url": result.source}),
            tags=f"auto_classified:{result.document_type},source:url" if result.document_type else "source:url",
            uploaded_by=str(ctx.user_id),
            tenant_id=tenant,
        )
        db.add(doc_record)
        await db.flush()
        stored.append({
            "document_id": doc_record.id,
            "source": result.source,
            "format": result.doc_format,
            "document_type": result.document_type,
            "confidence": result.confidence,
            "entities_count": len(result.entities),
            "links_count": len(result.links),
            "processing_time_ms": result.processing_time_ms,
        })

    await db.commit()
    return {
        "status": "processed",
        "url": url,
        "crawl": crawl,
        "documents_found": sum(1 for s in stored if "document_id" in s),
        "documents": stored,
    }


# ── Web-Intel Ingest (Firecrawl) ──────────────────────────────────────

@router.post("/web-intel-ingest")
async def web_intel_ingest(
    url: str = Form(...),
    doc_type_hint: Optional[str] = Form(None),
    contract_id: Optional[int] = Form(None),
    ctx: AuthContext = Depends(write_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a URL through the shared Firecrawl client (clean markdown) and run it
    through the compliance understanding pipeline. The URL is validated first."""
    from services.common.firecrawl import FirecrawlClient, FirecrawlUnavailable
    from services.compliance.document_architect import InputType

    try:
        await safe_fetch.check_url(url)
    except safe_fetch.FetchRefused as e:
        raise HTTPException(400, f"URL refused: {e}")
    await crud.assert_owned(db, ctx, Contract, contract_id, "Contract")

    client = FirecrawlClient()
    try:
        scraped = await client.scrape(url)
    except FirecrawlUnavailable as e:
        raise HTTPException(502, f"Web-intel extraction unavailable: {e}")

    markdown = FirecrawlClient.markdown_from(scraped)
    if not markdown:
        raise HTTPException(422, "Firecrawl returned no extractable content for the URL")

    tenant = tenant_str(ctx)
    result = await _architect().process_file(
        content=markdown.encode("utf-8"),
        filename="web-intel.md",
        tenant_id=tenant,
        doc_type_hint=doc_type_hint,
        contract_id=contract_id,
    )
    result.source = url
    result.input_type = InputType.url_fetch.value

    doc_record = ComplianceDocument(
        title=result.title or (urlparse(url).netloc or "web page"),
        document_type=_map_doc_type(result.document_type),
        file_path=result.stored_path or None,
        file_size=len(markdown.encode("utf-8")),
        mime_type="text/markdown",
        ocr_text=result.cleaned_text[:50000] if result.cleaned_text else None,
        extracted_data=json.dumps({
            "entities": [{"label": e.label, "value": e.value} for e in result.entities],
            "links": [{"url": l.url, "type": l.link_type} for l in result.links],
            "references": result.references,
            "source_url": url,
        }, default=str),
        tags=f"auto_classified:{result.document_type},source:web-intel" if result.document_type else "source:web-intel",
        uploaded_by=str(ctx.user_id),
        tenant_id=tenant,
        contract_id=contract_id,
    )
    db.add(doc_record)
    await db.commit()
    await db.refresh(doc_record)

    return {
        "status": "processed",
        "source": "firecrawl",
        "document_id": doc_record.id,
        "understanding": {
            "doc_id": result.doc_id,
            "title": result.title,
            "document_type": result.document_type,
            "compliance_category": result.compliance_category,
            "confidence": result.confidence,
            "entities_count": len(result.entities),
            "links_count": len(result.links),
            "markdown_preview": result.markdown[:1000] if result.markdown else "",
            "processing_time_ms": result.processing_time_ms,
            "errors": result.errors,
        },
    }


# ── Document List & Detail ────────────────────────────────────────────

@router.get("/")
async def list_documents(
    document_type: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    q = crud.scoped_select(ComplianceDocument, ctx)
    if document_type:
        q = q.where(ComplianceDocument.document_type == document_type)
    if contract_id:
        q = q.where(ComplianceDocument.contract_id == contract_id)
    q = q.order_by(ComplianceDocument.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    docs = (await db.execute(q)).scalars().all()
    return {
        "items": [_doc_to_dict(d) for d in docs],
        "page": page,
        "page_size": page_size,
    }


@router.get("/stats/summary")
async def document_stats(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """Get document processing statistics."""
    docs = await crud.list_rows(db, ctx, ComplianceDocument)

    by_type: dict = {}
    with_financials = 0
    with_entities = 0
    total_size = 0
    for d in docs:
        key = getattr(d.document_type, "value", d.document_type)
        by_type[key] = by_type.get(key, 0) + 1
        if d.financial_summary:
            with_financials += 1
        if d.extracted_data:
            with_entities += 1
        total_size += d.file_size or 0

    return {
        "total_documents": len(docs),
        "by_type": by_type,
        "with_financials": with_financials,
        "with_entities": with_entities,
        "total_size_bytes": total_size,
    }


@router.get("/{doc_id}")
async def get_document_detail(doc_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    doc = await crud.get_owned(db, ctx, ComplianceDocument, doc_id, "Document")
    return _doc_to_dict(doc, full=True)


# ── Re-process Document ───────────────────────────────────────────────

@router.post("/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: int,
    doc_type_hint: Optional[str] = Query(None),
    ctx: AuthContext = Depends(write_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Re-process a stored document through the understanding architect."""
    doc = await crud.get_owned(db, ctx, ComplianceDocument, doc_id, "Document")
    if not doc.ocr_text:
        raise HTTPException(400, "Document has no text content to re-process")

    new_result = await _architect().process_file(
        content=doc.ocr_text.encode("utf-8"),
        filename="reprocess.txt",
        tenant_id=tenant_str(ctx),
        doc_type_hint=doc_type_hint,
    )

    doc.extracted_data = json.dumps({
        "entities": [{"label": e.label, "value": e.value, "confidence": e.confidence} for e in new_result.entities],
        "financials": [{"amount": f.amount, "currency": f.currency, "line_item": f.line_item} for f in new_result.financials],
        "links": [{"url": l.url, "type": l.link_type} for l in new_result.links],
        "references": new_result.references,
    }, default=str)
    doc.tags = f"reprocessed,auto_classified:{new_result.document_type}"
    await db.commit()

    return {"status": "reprocessed", "document_id": doc_id, "entities_found": len(new_result.entities)}


# ── Link Document to Contract ─────────────────────────────────────────

@router.post("/{doc_id}/link-contract")
async def link_document_to_contract(
    doc_id: int,
    contract_id: int = Form(...),
    ctx: AuthContext = Depends(write_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Link a document to a contract (both must belong to the caller's tenant)."""
    doc = await crud.get_owned(db, ctx, ComplianceDocument, doc_id, "Document")
    await crud.get_owned(db, ctx, Contract, contract_id, "Contract")
    doc.contract_id = contract_id
    await db.commit()
    return {"status": "linked", "document_id": doc_id, "contract_id": contract_id}


# ── Helpers ───────────────────────────────────────────────────────────

def _map_doc_type(architect_type: str) -> str:
    """Map architect document_type to database DocumentType enum."""
    mapping = {
        "contract": DocumentType.contract.value,
        "tax_return": DocumentType.tax_return.value,
        "hs_report": DocumentType.hs_report.value,
        "cipc_filing": DocumentType.cipc_filing.value,
        "bbbee_certificate": DocumentType.bbbee_certificate.value,
        "permit": DocumentType.permit.value,
        "dr_plan": DocumentType.dr_plan.value,
        "bcp_plan": DocumentType.bcp_plan.value,
        "financial_statement": DocumentType.financial_statement.value,
        "invoice": DocumentType.invoice.value,
        "policy": DocumentType.policy.value,
        "breach_report": DocumentType.other.value,
        "dsar": DocumentType.other.value,
        "icasa_submission": DocumentType.other.value,
        "eservices_form": DocumentType.other.value,
    }
    return mapping.get(architect_type, DocumentType.other.value)


def _doc_to_dict(doc: ComplianceDocument, full: bool = False) -> dict:
    d = {
        "id": doc.id,
        "title": doc.title,
        "document_type": getattr(doc.document_type, "value", doc.document_type),
        "file_path": doc.file_path if (doc.file_path or "").startswith(("http://", "https://")) else None,
        "file_size": doc.file_size,
        "mime_type": doc.mime_type,
        "contract_id": doc.contract_id,
        "tags": doc.tags,
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }
    if full:
        d["ocr_text"] = doc.ocr_text[:5000] if doc.ocr_text else None
        d["extracted_data"] = _safe_json(doc.extracted_data)
        d["financial_summary"] = _safe_json(doc.financial_summary)
    return d


def _safe_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
