"""
Compliance Service — Document Upload & Understanding Routes
Handles file uploads, URL fetches, website crawls, OCR processing,
entity extraction, and document linking to compliance records.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_async_session as get_db
from services.compliance.database import (
    ComplianceDocument, DocumentType, Contract,
)
from services.compliance.document_architect import (
    DocumentUnderstandingArchitect, get_architect,
)

router = APIRouter(prefix="/documents", tags=["documents"])


# ── File Upload ────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Form("default"),
    doc_type_hint: Optional[str] = Form(None),
    contract_id: Optional[int] = Form(None),
    process: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document and optionally process it through the understanding architect."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    architect = get_architect()
    result = await architect.process_file(
        content=content,
        filename=file.filename or "uploaded_file",
        tenant_id=tenant_id,
        doc_type_hint=doc_type_hint,
        contract_id=contract_id,
    )

    # Store document record in DB
    doc_record = ComplianceDocument(
        title=file.filename or "Untitled",
        document_type=_map_doc_type(result.document_type),
        file_path=f"/opt/data/uploads/compliance/{tenant_id}/{result.doc_id}_{file.filename}",
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
        tenant_id=tenant_id,
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
            "source": result.source,
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
    tenant_id: str = Form("default"),
    doc_type_hint: Optional[str] = Form(None),
    crawl: bool = Form(False),
    max_depth: int = Form(2),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a document from a URL and process it."""
    architect = get_architect()
    results = await architect.process_url(
        url=url,
        tenant_id=tenant_id,
        crawl=crawl,
        max_depth=max_depth,
        doc_type_hint=doc_type_hint,
    )

    stored = []
    for result in results:
        doc_record = ComplianceDocument(
            title=result.title or result.source,
            document_type=_map_doc_type(result.document_type),
            file_path=result.source,
            file_size=result.file_size_bytes,
            mime_type="text/html" if result.doc_format == "html" else "application/octet-stream",
            ocr_text=result.cleaned_text[:50000] if result.cleaned_text else None,
            extracted_data=json.dumps({
                "entities": [{"label": e.label, "value": e.value} for e in result.entities],
                "links": [{"url": l.url, "type": l.link_type} for l in result.links],
                "references": result.references,
            }, default=str) if result.entities else None,
            tags=f"auto_classified:{result.document_type},source:url" if result.document_type else "source:url",
            tenant_id=tenant_id,
        )
        db.add(doc_record)
        await db.refresh(doc_record)
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
        "documents_found": len(stored),
        "documents": stored,
    }


# ── Document List & Detail ────────────────────────────────────────────

@router.get("/")
async def list_documents(
    document_type: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    tenant_id: str = Query("default"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceDocument).where(ComplianceDocument.tenant_id == tenant_id)
    if document_type:
        q = q.where(ComplianceDocument.document_type == document_type)
    if contract_id:
        q = q.where(ComplianceDocument.contract_id == contract_id)
    q = q.order_by(ComplianceDocument.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    docs = result.scalars().all()
    return {
        "items": [_doc_to_dict(d) for d in docs],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{doc_id}")
async def get_document_detail(
    doc_id: int,
    tenant_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ComplianceDocument).where(ComplianceDocument.id == doc_id).where(ComplianceDocument.tenant_id == tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return _doc_to_dict(doc, full=True)


# ── Re-process Document ───────────────────────────────────────────────

@router.post("/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: int,
    tenant_id: str = Query("default"),
    doc_type_hint: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Re-process a stored document through the understanding architect."""
    result = await db.execute(
        select(ComplianceDocument).where(ComplianceDocument.id == doc_id).where(ComplianceDocument.tenant_id == tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    if not doc.ocr_text:
        raise HTTPException(400, "Document has no text content to re-process")

    architect = get_architect()
    # Re-process from stored text
    new_result = await architect.process_file(
        content=doc.ocr_text.encode("utf-8"),
        filename=doc.title,
        tenant_id=tenant_id,
        doc_type_hint=doc_type_hint,
    )

    # Update record
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
    tenant_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Link a document to a contract."""
    doc_result = await db.execute(
        select(ComplianceDocument).where(ComplianceDocument.id == doc_id).where(ComplianceDocument.tenant_id == tenant_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    contract_result = await db.execute(
        select(Contract).where(Contract.id == contract_id).where(Contract.tenant_id == tenant_id)
    )
    contract = contract_result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")

    doc.contract_id = contract_id
    await db.commit()
    return {"status": "linked", "document_id": doc_id, "contract_id": contract_id}


# ── Document Stats ────────────────────────────────────────────────────

@router.get("/stats/summary")
async def document_stats(
    tenant_id: str = Query("default"),
    db: AsyncSession = Depends(get_db),
):
    """Get document processing statistics."""
    result = await db.execute(
        select(ComplianceDocument).where(ComplianceDocument.tenant_id == tenant_id)
    )
    docs = result.scalars().all()

    total = len(docs)
    by_type = {}
    with_financials = 0
    with_entities = 0
    total_size = 0

    for d in docs:
        by_type[d.document_type] = by_type.get(d.document_type, 0) + 1
        if d.financial_summary:
            with_financials += 1
        if d.extracted_data:
            with_entities += 1
        total_size += d.file_size or 0

    return {
        "total_documents": total,
        "by_type": by_type,
        "with_financials": with_financials,
        "with_entities": with_entities,
        "total_size_bytes": total_size,
    }


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
        "document_type": doc.document_type,
        "file_path": doc.file_path,
        "file_size": doc.file_size,
        "mime_type": doc.mime_type,
        "contract_id": doc.contract_id,
        "tags": doc.tags,
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }
    if full:
        d["ocr_text"] = doc.ocr_text[:5000] if doc.ocr_text else None
        d["extracted_data"] = json.loads(doc.extracted_data) if doc.extracted_data else None
        d["financial_summary"] = json.loads(doc.financial_summary) if doc.financial_summary else None
    return d
