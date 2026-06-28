"""
Compliance Service — DR/BCP, Compliance Scoring, e-Services, Documents, Financial Scenarios
"""
import json
import logging
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from services.common.db import get_db
from services.compliance.database import (
    DrBcpPlan, DrBcpAssessment, DrBcpStatus,
    ComplianceScore, ComplianceObligation, ComplianceCategory, ComplianceStatus,
    EserviceSubmission, EservicePlatform, EserviceSubmissionStatus,
    ComplianceDocument, DocumentType,
    FinancialScenario,
)

router = APIRouter()


# ── DR/BCP ──────────────────────────────────────────────────────────────

dr_router = APIRouter(prefix="/dr-bcp", tags=["dr-bcp"])


@dr_router.get("/plans")
async def list_dr_bcp_plans(
    plan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(DrBcpPlan)
    if plan_type:
        q = q.where(DrBcpPlan.plan_type == plan_type)
    if status:
        q = q.where(DrBcpPlan.status == status)
    result = await db.execute(q)
    return {"items": [p.to_dict() for p in result.scalars().all()]}


@dr_router.post("/plans")
async def create_dr_bcp_plan(body: dict, db: AsyncSession = Depends(get_db)):
    plan = DrBcpPlan(**body)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan.to_dict()


@dr_router.get("/plans/{plan_id}")
async def get_dr_bcp_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DrBcpPlan).where(DrBcpPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan.to_dict()


@dr_router.put("/plans/{plan_id}")
async def update_dr_bcp_plan(plan_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DrBcpPlan).where(DrBcpPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    for k, v in body.items():
        setattr(plan, k, v)
    await db.commit()
    await db.refresh(plan)
    return plan.to_dict()


@dr_router.post("/plans/{plan_id}/assessments")
async def create_dr_bcp_assessment(plan_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    body["plan_id"] = plan_id
    assessment = DrBcpAssessment(**body)
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment.to_dict()


@dr_router.get("/plans/{plan_id}/assessments")
async def list_dr_bcp_assessments(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DrBcpAssessment)
        .where(DrBcpAssessment.plan_id == plan_id)
        .order_by(DrBcpAssessment.assessment_date.desc())
    )
    return {"items": [a.to_dict() for a in result.scalars().all()]}


@dr_router.get("/dashboard")
async def dr_bcp_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DrBcpPlan))
    plans = result.scalars().all()
    total = len(plans)
    tested = sum(1 for p in plans if p.status == DrBcpStatus.tested)
    approved = sum(1 for p in plans if p.status == DrBcpStatus.approved)
    failed = sum(1 for p in plans if p.status == DrBcpStatus.failed)
    return {"total": total, "tested": tested, "approved": approved, "failed": failed}


# ── Compliance Scoring ──────────────────────────────────────────────────

score_router = APIRouter(prefix="/scores", tags=["scores"])


@score_router.get("/")
async def list_compliance_scores(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceScore)
    if category:
        q = q.where(ComplianceScore.category == category)
    q = q.order_by(ComplianceScore.calculated_at.desc())
    result = await db.execute(q)
    return {"items": [s.to_dict() for s in result.scalars().all()]}


@score_router.post("/calculate")
async def calculate_compliance_scores(db: AsyncSession = Depends(get_db)):
    """Calculate compliance scores across all categories."""
    scores = []
    for cat in ComplianceCategory:
        # Count obligations
        obl_result = await db.execute(
            select(ComplianceObligation).where(ComplianceObligation.category == cat)
        )
        obligations = obl_result.scalars().all()
        total = len(obligations)
        if total == 0:
            score = 100.0
            status = ComplianceStatus.exempt
            issues = 0
            critical = 0
        else:
            compliant = sum(1 for o in obligations if o.status == ComplianceStatus.compliant)
            non_compliant = sum(1 for o in obligations if o.status == ComplianceStatus.non_compliant)
            at_risk = sum(1 for o in obligations if o.status == ComplianceStatus.at_risk)
            score = (compliant / total) * 100 if total > 0 else 100
            issues = non_compliant + at_risk
            critical = non_compliant
            if score >= 90:
                status = ComplianceStatus.compliant
            elif score >= 70:
                status = ComplianceStatus.at_risk
            else:
                status = ComplianceStatus.non_compliant

        cs = ComplianceScore(
            category=cat,
            score=round(score, 2),
            status=status,
            issues_count=issues,
            critical_issues=critical,
        )
        db.add(cs)
        scores.append({"category": cat.value, "score": round(score, 2), "status": status.value})

    await db.commit()
    return {"scores": scores, "calculated_at": datetime.utcnow().isoformat()}


@score_router.get("/obligations")
async def list_obligations(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceObligation)
    if category:
        q = q.where(ComplianceObligation.category == category)
    if status:
        q = q.where(ComplianceObligation.status == status)
    q = q.order_by(ComplianceObligation.due_date)
    result = await db.execute(q)
    return {"items": [o.to_dict() for o in result.scalars().all()]}


@score_router.post("/obligations")
async def create_obligation(body: dict, db: AsyncSession = Depends(get_db)):
    obl = ComplianceObligation(**body)
    db.add(obl)
    await db.commit()
    await db.refresh(obl)
    return obl.to_dict()


@score_router.put("/obligations/{obl_id}")
async def update_obligation(obl_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ComplianceObligation).where(ComplianceObligation.id == obl_id))
    obl = result.scalar_one_or_none()
    if not obl:
        raise HTTPException(404, "Obligation not found")
    for k, v in body.items():
        setattr(obl, k, v)
    await db.commit()
    await db.refresh(obl)
    return obl.to_dict()


# ── e-Services Gateway ──────────────────────────────────────────────────

eservice_router = APIRouter(prefix="/eservices", tags=["eservices"])


@eservice_router.get("/submissions")
async def list_eservice_submissions(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(EserviceSubmission)
    if platform:
        q = q.where(EserviceSubmission.platform == platform)
    if status:
        q = q.where(EserviceSubmission.status == status)
    q = q.order_by(EserviceSubmission.created_at.desc())
    result = await db.execute(q)
    return {"items": [s.to_dict() for s in result.scalars().all()]}


@eservice_router.post("/submissions")
async def create_eservice_submission(body: dict, db: AsyncSession = Depends(get_db)):
    sub = EserviceSubmission(**body)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub.to_dict()


@eservice_router.post("/submissions/{sub_id}/submit")
async def submit_to_platform(sub_id: int, db: AsyncSession = Depends(get_db)):
    """Submit form to external e-Services platform."""
    result = await db.execute(select(EserviceSubmission).where(EserviceSubmission.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Submission not found")
    # In production, this would call the actual platform API
    sub.status = EserviceSubmissionStatus.submitted
    sub.submission_date = datetime.utcnow()
    await db.commit()
    return {"status": "submitted", "id": sub_id, "platform": sub.platform.value}


@eservice_router.get("/platforms")
async def list_platforms():
    return {"platforms": [p.value for p in EservicePlatform]}


# ── Document Understanding ──────────────────────────────────────────────

doc_router = APIRouter(prefix="/documents", tags=["documents"])


@doc_router.get("/")
async def list_documents(
    document_type: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceDocument)
    if document_type:
        q = q.where(ComplianceDocument.document_type == document_type)
    if contract_id:
        q = q.where(ComplianceDocument.contract_id == contract_id)
    q = q.order_by(ComplianceDocument.created_at.desc())
    result = await db.execute(q)
    return {"items": [d.to_dict() for d in result.scalars().all()]}


@doc_router.post("/")
async def create_document(body: dict, db: AsyncSession = Depends(get_db)):
    doc = ComplianceDocument(**body)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc.to_dict()


@doc_router.post("/{doc_id}/ocr")
async def process_document_ocr(doc_id: int, db: AsyncSession = Depends(get_db)):
    """Process document with OCR and extract structured data.

    Primary pipeline: DocumentUnderstandingArchitect (pymupdf text + entity extraction).
    Fallback: pytesseract + pdf2image for image-only PDFs / raster images.
    """
    result = await db.execute(select(ComplianceDocument).where(ComplianceDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = doc.file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(422, f"Document file not found on disk: {file_path!r}")

    ocr_text: str = ""
    extracted: dict = {}

    # ── Primary: DocumentUnderstandingArchitect (pymupdf) ──────────────
    try:
        import aiofiles
        from services.compliance.document_architect import DocumentUnderstandingArchitect

        async with aiofiles.open(file_path, "rb") as fh:
            content = await fh.read()

        architect = DocumentUnderstandingArchitect()
        understanding = await architect.process_file(
            content=content,
            filename=os.path.basename(file_path),
            tenant_id=doc.tenant_id,
        )

        ocr_text = understanding.cleaned_text or understanding.raw_text
        extracted = {
            "entities": [
                {"label": e.label, "value": e.value, "confidence": e.confidence}
                for e in understanding.entities
            ],
            "financials": [
                {
                    "amount": f.amount,
                    "currency": f.currency,
                    "context": f.context,
                    "line_item": f.line_item,
                }
                for f in understanding.financials
            ],
            "dates": understanding.dates,
            "references": understanding.references,
            "document_type": understanding.document_type,
            "compliance_category": understanding.compliance_category,
            "page_count": understanding.page_count,
            "errors": understanding.errors,
            "processing_time_ms": understanding.processing_time_ms,
        }

        # If pymupdf got no text (scanned PDF / image), fall through to Tesseract
        if not ocr_text.strip():
            raise ValueError("pymupdf extracted no text — falling back to Tesseract")

    except Exception as primary_err:
        logger.warning("Primary OCR pipeline failed for doc %d: %s", doc_id, primary_err)

        # ── Fallback: pytesseract + pdf2image ──────────────────────────
        try:
            mime = (doc.mime_type or "").lower()
            is_pdf = "pdf" in mime or file_path.lower().endswith(".pdf")
            is_image = "image" in mime or any(
                file_path.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif")
            )
            ocr_text = ""
            if is_pdf:
                import pdf2image
                images = pdf2image.convert_from_bytes(await asyncio.to_thread(open, file_path, "rb") and open(file_path, "rb").read())
                import pytesseract
                for img in images:
                    ocr_text += pytesseract.image_to_string(img) + "\n"
            elif is_image:
                from PIL import Image
                import pytesseract
                img = Image.open(file_path)
                ocr_text = pytesseract.image_to_string(img)
            else:
                ocr_text = ""

            if not ocr_text.strip():
                raise ValueError("Tesseract extracted no text")

        except Exception as fallback_err:
            logger.error("Fallback OCR also failed for doc %d: %s", doc_id, fallback_err)
            return JSONResponse(
                status_code=422,
                content={"error": "OCR failed", "detail": str(fallback_err)},
            )

    doc.ocr_text = ocr_text.strip()
    doc.extracted_entities = "{}"
    doc.financial_summary = "{}"
    await db.commit()

    return {"status": "processed", "id": doc_id, "char_count": len(ocr_text)}
