"""
Compliance Service — DR/BCP, Compliance Scoring, e-Services, Documents

Tenant-scoped, explicit request schemas, role tiers (reads: any member; writes:
compliance_officer / manager / admin).
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud, scoring, upload_safety
from services.compliance.access import member_ctx, tenant_str, write_ctx
from services.compliance.database import (
    DrBcpPlan, DrBcpAssessment, DrBcpStatus,
    ComplianceScore, ComplianceObligation, ComplianceCategory, ComplianceStatus,
    EserviceSubmission, EservicePlatform, EserviceSubmissionStatus,
    ComplianceDocument, Contract,
)
from services.compliance.write_schemas import create_schema, dump_set, update_schema

logger = logging.getLogger(__name__)

router = APIRouter()

DrBcpPlanIn = create_schema(DrBcpPlan)
DrBcpPlanPatch = update_schema(DrBcpPlan)
DrBcpAssessmentIn = create_schema(DrBcpAssessment, protected=("plan_id",))
ObligationIn = create_schema(ComplianceObligation)
ObligationPatch = update_schema(ComplianceObligation)
EserviceSubmissionIn = create_schema(
    EserviceSubmission,
    protected=("status", "submission_date", "response_date", "reference_number", "response_data",
               "error_message", "retry_count"),
)
# Metadata only: file_path / size / OCR output are set by the upload pipeline, never by a client.
DocumentMetaIn = create_schema(
    ComplianceDocument,
    protected=("file_path", "file_size", "mime_type", "ocr_text", "extracted_data", "financial_summary", "uploaded_by"),
)


class EserviceSubmitIn(BaseModel):
    """A person submitted this form on the external platform and pastes the reference it gave them."""
    model_config = ConfigDict(extra="forbid")
    reference_number: str = Field(min_length=3, max_length=200)


# ── DR/BCP ──────────────────────────────────────────────────────────────

dr_router = APIRouter(prefix="/dr-bcp", tags=["dr-bcp"])


@dr_router.get("/plans")
async def list_dr_bcp_plans(
    plan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if plan_type:
        where.append(DrBcpPlan.plan_type == plan_type)
    if status:
        where.append(DrBcpPlan.status == status)
    rows = await crud.list_rows(db, ctx, DrBcpPlan, *where)
    return {"items": [p.to_dict() for p in rows]}


@dr_router.post("/plans")
async def create_dr_bcp_plan(body: DrBcpPlanIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, DrBcpPlan, dump_set(body))).to_dict()


@dr_router.get("/plans/{plan_id}")
async def get_dr_bcp_plan(plan_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.get_owned(db, ctx, DrBcpPlan, plan_id, "Plan")).to_dict()


@dr_router.put("/plans/{plan_id}")
async def update_dr_bcp_plan(plan_id: int, body: DrBcpPlanPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, DrBcpPlan, plan_id, dump_set(body), "Plan")).to_dict()


@dr_router.post("/plans/{plan_id}/assessments")
async def create_dr_bcp_assessment(plan_id: int, body: DrBcpAssessmentIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    await crud.get_owned(db, ctx, DrBcpPlan, plan_id, "Plan")
    data = dump_set(body)
    data["plan_id"] = plan_id
    return (await crud.create_row(db, ctx, DrBcpAssessment, data)).to_dict()


@dr_router.get("/plans/{plan_id}/assessments")
async def list_dr_bcp_assessments(plan_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    await crud.get_owned(db, ctx, DrBcpPlan, plan_id, "Plan")
    rows = await crud.list_rows(
        db, ctx, DrBcpAssessment, DrBcpAssessment.plan_id == plan_id,
        order_by=DrBcpAssessment.assessment_date.desc(),
    )
    return {"items": [a.to_dict() for a in rows]}


@dr_router.get("/dashboard")
async def dr_bcp_dashboard(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    plans = await crud.list_rows(db, ctx, DrBcpPlan)
    return {
        "total": len(plans),
        "tested": sum(1 for p in plans if p.status == DrBcpStatus.tested),
        "approved": sum(1 for p in plans if p.status == DrBcpStatus.approved),
        "failed": sum(1 for p in plans if p.status == DrBcpStatus.failed),
    }


# ── Compliance Scoring ──────────────────────────────────────────────────

score_router = APIRouter(prefix="/scores", tags=["scores"])


@score_router.get("/")
async def list_compliance_scores(
    category: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [ComplianceScore.category == category] if category else []
    rows = await crud.list_rows(db, ctx, ComplianceScore, *where, order_by=ComplianceScore.calculated_at.desc())
    return {"items": [s.to_dict() for s in rows]}


@score_router.get("/latest")
async def latest_compliance_scores(ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    """Newest snapshot per category; categories never assessed are listed as not_assessed (score null)."""
    rows = await crud.list_rows(db, ctx, ComplianceScore, order_by=ComplianceScore.calculated_at.desc())
    latest = {r.category.value: r for r in scoring.latest_per_category(rows)}
    items = []
    for cat in ComplianceCategory:
        r = latest.get(cat.value)
        items.append(
            r.to_dict() if r else {"category": cat.value, "score": None, "status": "not_assessed"}
        )
    return {"items": items, "overall_score": scoring.overall_score(latest.values())}


@score_router.post("/calculate")
async def calculate_compliance_scores(ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Calculate compliance scores from THIS tenant's obligations.

    A category with no obligations is not assessed: it gets no stored score and is reported
    as score null / status not_assessed (never 100 / exempt)."""
    scores = []
    tenant = tenant_str(ctx)
    for cat in ComplianceCategory:
        obligations = await crud.list_rows(db, ctx, ComplianceObligation, ComplianceObligation.category == cat)
        calc = scoring.score_category(o.status for o in obligations)
        if calc is None:
            scores.append({"category": cat.value, "score": None, "status": "not_assessed"})
            continue
        db.add(ComplianceScore(
            tenant_id=tenant,
            category=cat,
            score=calc["score"],
            status=ComplianceStatus(calc["status"]),
            issues_count=calc["issues"],
            critical_issues=calc["critical"],
        ))
        scores.append({"category": cat.value, "score": calc["score"], "status": calc["status"]})

    await db.commit()
    return {"scores": scores, "calculated_at": datetime.utcnow().isoformat()}


@score_router.get("/obligations")
async def list_obligations(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if category:
        where.append(ComplianceObligation.category == category)
    if status:
        where.append(ComplianceObligation.status == status)
    rows = await crud.list_rows(db, ctx, ComplianceObligation, *where, order_by=ComplianceObligation.due_date)
    return {"items": [o.to_dict() for o in rows]}


@score_router.post("/obligations")
async def create_obligation(body: ObligationIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, ComplianceObligation, dump_set(body))).to_dict()


@score_router.put("/obligations/{obl_id}")
async def update_obligation(obl_id: int, body: ObligationPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, ComplianceObligation, obl_id, dump_set(body), "Obligation")).to_dict()


# ── e-Services Gateway ──────────────────────────────────────────────────

eservice_router = APIRouter(prefix="/eservices", tags=["eservices"])


@eservice_router.get("/submissions")
async def list_eservice_submissions(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if platform:
        where.append(EserviceSubmission.platform == platform)
    if status:
        where.append(EserviceSubmission.status == status)
    rows = await crud.list_rows(db, ctx, EserviceSubmission, *where, order_by=EserviceSubmission.created_at.desc())
    return {"items": [s.to_dict() for s in rows]}


@eservice_router.post("/submissions")
async def create_eservice_submission(body: EserviceSubmissionIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, ComplianceObligation, data.get("obligation_id"), "Obligation")
    return (await crud.create_row(db, ctx, EserviceSubmission, data)).to_dict()


@eservice_router.post("/submissions/{sub_id}/submit")
async def submit_to_platform(sub_id: int, body: EserviceSubmitIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Record that a person submitted this form on the external platform.

    Nothing is sent from here: the reference number must be the real one the platform
    issued (previously this marked the form 'submitted' without contacting anyone)."""
    sub = await crud.get_owned(db, ctx, EserviceSubmission, sub_id, "Submission")
    sub.status = EserviceSubmissionStatus.submitted
    sub.submission_date = datetime.utcnow()
    sub.reference_number = body.reference_number
    await db.commit()
    return {"status": "submitted", "id": sub_id, "platform": sub.platform.value, "reference_number": body.reference_number,
            "note": "Recorded as submitted by a user; this service did not contact the platform."}


@eservice_router.get("/platforms")
async def list_platforms(ctx: AuthContext = Depends(member_ctx)):
    return {"platforms": [p.value for p in EservicePlatform]}


# ── Document Understanding ──────────────────────────────────────────────

doc_router = APIRouter(prefix="/documents", tags=["documents"])


@doc_router.get("/")
async def list_documents(
    document_type: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if document_type:
        where.append(ComplianceDocument.document_type == document_type)
    if contract_id:
        where.append(ComplianceDocument.contract_id == contract_id)
    rows = await crud.list_rows(db, ctx, ComplianceDocument, *where, order_by=ComplianceDocument.created_at.desc())
    items = []
    for d in rows:
        item = d.to_dict()
        item.pop("file_path", None)  # server storage paths are not exposed
        item.pop("ocr_text", None)
        items.append(item)
    return {"items": items}


@doc_router.post("/")
async def create_document(body: DocumentMetaIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Register document metadata. File content arrives only through /documents/upload."""
    data = dump_set(body)
    await crud.assert_owned(db, ctx, Contract, data.get("contract_id"), "Contract")
    data["uploaded_by"] = str(ctx.user_id)
    item = (await crud.create_row(db, ctx, ComplianceDocument, data)).to_dict()
    item.pop("file_path", None)
    return item


@doc_router.post("/{doc_id}/ocr")
async def process_document_ocr(doc_id: int, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    """Process a stored document with OCR and extract structured data.

    Primary pipeline: DocumentUnderstandingArchitect (pymupdf text + entity extraction).
    Fallback: pytesseract + pdf2image for image-only PDFs / raster images.
    Only files inside this tenant's own upload directory are ever read.
    """
    doc = await crud.get_owned(db, ctx, ComplianceDocument, doc_id, "Document")

    file_path = doc.file_path
    tenant_root = upload_safety.upload_root() / upload_safety.tenant_dir_name(ctx.tenant_id)
    if not file_path or not upload_safety.is_within(file_path, tenant_root) or not os.path.isfile(file_path):
        raise HTTPException(422, "Document file not found in storage")

    def _read() -> bytes:
        with open(file_path, "rb") as fh:
            return fh.read(upload_safety.max_upload_bytes() + 1)

    content = await asyncio.to_thread(_read)
    ocr_text: str = ""
    extracted: dict = {}

    try:
        from services.compliance.document_architect import DocumentUnderstandingArchitect

        understanding = await DocumentUnderstandingArchitect().process_file(
            content=content,
            filename=os.path.basename(file_path),
            tenant_id=tenant_str(ctx),
        )
        ocr_text = understanding.cleaned_text or understanding.raw_text
        extracted = {
            "entities": [{"label": e.label, "value": e.value, "confidence": e.confidence} for e in understanding.entities],
            "dates": understanding.dates,
            "references": understanding.references,
            "document_type": understanding.document_type,
            "page_count": understanding.page_count,
        }
        if not ocr_text.strip():
            raise ValueError("pymupdf extracted no text; falling back to Tesseract")
    except Exception as primary_err:
        logger.warning("Primary OCR pipeline failed for doc %d: %s", doc_id, primary_err)
        try:
            lower = file_path.lower()
            ocr_text = ""
            if lower.endswith(".pdf"):
                import pdf2image
                import pytesseract
                for img in await asyncio.to_thread(pdf2image.convert_from_bytes, content):
                    ocr_text += pytesseract.image_to_string(img) + "\n"
            elif lower.endswith((".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif")):
                import io
                import pytesseract
                from PIL import Image
                ocr_text = pytesseract.image_to_string(Image.open(io.BytesIO(content)))
            if not ocr_text.strip():
                raise ValueError("Tesseract extracted no text")
        except Exception as fallback_err:
            logger.error("Fallback OCR also failed for doc %d: %s", doc_id, fallback_err)
            return JSONResponse(status_code=422, content={"error": "OCR failed", "detail": "No text could be extracted"})

    doc.ocr_text = ocr_text.strip()
    if extracted:
        doc.extracted_data = json.dumps(extracted, default=str)
    await db.commit()

    return {"status": "processed", "id": doc_id, "char_count": len(ocr_text)}
