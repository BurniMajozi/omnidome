"""FNO order management and automation routes.

Handles placing orders with SA FNOs (Vumatel, Openserve, MetroFibre,
Frogfoot, Octotel), tracking order status, and running automation jobs.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.network.adapters.factory import FNOFactory
from services.network.database import get_session
from services.network.models import AutomationJob, FNOOrder, NetworkService
from services.network.schemas import (
    AutomationJobCreate,
    AutomationJobRead,
    FNOOrderCreate,
    FNOOrderRead,
    FNOOrderUpdate,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fno", tags=["FNO Orders"])


# ---------------------------------------------------------------------------
# FNO config — loaded from env or defaults for dev
# ---------------------------------------------------------------------------

def _load_fno_configs() -> Dict[str, Dict[str, Any]]:
    """Load FNO connection configs from environment variables."""
    return {
        "vumatel": {
            "api_key": os.getenv("FNO_VUMATEL_API_KEY", ""),
            "base_url": os.getenv("FNO_VUMATEL_BASE_URL", "https://api.vumatel.co.za/v1"),
        },
        "openserve": {
            "portal_url": os.getenv("FNO_OPENSERVE_PORTAL_URL", "https://connect.openserve.co.za"),
            "credentials": {
                "user": os.getenv("FNO_OPENSERVE_USER", ""),
                "pass": os.getenv("FNO_OPENSERVE_PASS", ""),
            },
        },
        "metrofibre": {
            "api_key": os.getenv("FNO_METROFIBRE_API_KEY", ""),
            "base_url": os.getenv("FNO_METROFIBRE_BASE_URL", "https://api.metrofibre.co.za/v1"),
        },
        "frogfoot": {
            "api_key": os.getenv("FNO_FROGFOOT_API_KEY", ""),
            "base_url": os.getenv("FNO_FROGFOOT_BASE_URL", "https://api.frogfoot.com/v2"),
        },
        "octotel": {
            "api_key": os.getenv("FNO_OCTOTEL_API_KEY", ""),
            "base_url": os.getenv("FNO_OCTOTEL_BASE_URL", "https://api.octotel.co.za/v1"),
        },
    }


def _get_adapter(fno_provider: str):
    configs = _load_fno_configs()
    config = configs.get(fno_provider, {})
    return FNOFactory.get_adapter(fno_provider, config)


# ---------------------------------------------------------------------------
# FNO ORDERS — CRUD
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=FNOOrderRead, status_code=status.HTTP_201_CREATED)
async def create_fno_order(
    payload: FNOOrderCreate,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth_context),
):
    """Create and submit an order to an FNO (new install, migration, speed change, cancel)."""
    with get_session() as session:
        # Verify service exists
        svc = session.execute(
            select(NetworkService).where(
                NetworkService.id == payload.service_id,
                NetworkService.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Network service not found")

        order = FNOOrder(
            tenant_id=auth.tenant_id,
            service_id=payload.service_id,
            fno_provider=payload.fno_provider,
            order_type=payload.order_type,
            scheduled_date=payload.scheduled_date,
            request_payload=payload.request_payload,
        )
        session.add(order)
        session.flush()
        session.refresh(order)

        order_id = order.id
        fno = payload.fno_provider
        order_type = payload.order_type

        logger.info("Created FNO order %s [%s/%s] for service %s", order_id, fno, order_type, payload.service_id)

        # Dispatch async FNO call
        background_tasks.add_task(
            _execute_fno_order, order_id, fno, order_type, payload.request_payload or {}, auth.tenant_id,
        )
        return FNOOrderRead.model_validate(order)


async def _execute_fno_order(
    order_id: uuid.UUID,
    fno_provider: str,
    order_type: str,
    request_payload: dict,
    tenant_id: uuid.UUID,
):
    """Background task: call FNO adapter and update order status."""
    adapter = _get_adapter(fno_provider)
    try:
        if order_type == "new_installation":
            result = await adapter.place_order(request_payload.get("customer", {}), request_payload.get("plan_id", ""))
        elif order_type == "cancellation":
            result = await adapter.cancel_order(request_payload.get("fno_order_id", ""))
        elif order_type == "speed_change":
            result = await adapter.change_speed(
                request_payload.get("fno_account_id", ""),
                request_payload.get("new_profile", ""),
            )
        else:
            result = await adapter.place_order(request_payload.get("customer", {}), request_payload.get("plan_id", ""))

        new_status = "completed" if result.get("status") not in ("FAILED",) else "failed"
    except Exception as exc:
        logger.error("FNO order %s failed: %s", order_id, exc)
        result = {"error": str(exc)}
        new_status = "failed"

    # Persist result
    with get_session() as session:
        order = session.get(FNOOrder, order_id)
        if order:
            order.status = new_status
            order.response_payload = result
            order.error_message = result.get("error")
            if new_status == "completed":
                order.completed_date = datetime.now(timezone.utc)
                order.fno_reference = result.get("order_id", result.get("fno_account_id"))


@router.get("/orders", response_model=PaginatedResponse)
async def list_fno_orders(
    auth: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    fno_provider: Optional[str] = None,
):
    """List FNO orders for the current tenant."""
    with get_session() as session:
        q = select(FNOOrder).where(FNOOrder.tenant_id == auth.tenant_id)
        count_q = select(func.count(FNOOrder.id)).where(FNOOrder.tenant_id == auth.tenant_id)

        if service_id:
            q = q.where(FNOOrder.service_id == service_id)
            count_q = count_q.where(FNOOrder.service_id == service_id)
        if status_filter:
            q = q.where(FNOOrder.status == status_filter)
            count_q = count_q.where(FNOOrder.status == status_filter)
        if fno_provider:
            q = q.where(FNOOrder.fno_provider == fno_provider.lower())
            count_q = count_q.where(FNOOrder.fno_provider == fno_provider.lower())

        total = session.execute(count_q).scalar() or 0
        rows = session.execute(
            q.order_by(FNOOrder.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return PaginatedResponse(
            items=[FNOOrderRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/orders/{order_id}", response_model=FNOOrderRead)
async def get_fno_order(
    order_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        order = session.execute(
            select(FNOOrder).where(
                FNOOrder.id == order_id,
                FNOOrder.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="FNO order not found")
        return FNOOrderRead.model_validate(order)


@router.put("/orders/{order_id}", response_model=FNOOrderRead)
async def update_fno_order(
    order_id: uuid.UUID,
    payload: FNOOrderUpdate,
    auth: AuthContext = Depends(get_auth_context),
):
    """Manually update an FNO order (e.g. webhook callback, manual override)."""
    with get_session() as session:
        order = session.execute(
            select(FNOOrder).where(
                FNOOrder.id == order_id,
                FNOOrder.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="FNO order not found")

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(order, field, value)

        session.flush()
        session.refresh(order)
        return FNOOrderRead.model_validate(order)


# ---------------------------------------------------------------------------
# AUTOMATION JOBS — generic FNO automation
# ---------------------------------------------------------------------------

@router.post("/automation/jobs", response_model=AutomationJobRead, status_code=status.HTTP_202_ACCEPTED)
async def start_automation_job(
    payload: AutomationJobCreate,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth_context),
):
    """Trigger a generic FNO automation job (coverage check, provisioning, etc.)."""
    adapter = _get_adapter(payload.fno_provider)
    adapter_type = "api" if hasattr(adapter, "api_key") else "browser"

    with get_session() as session:
        job = AutomationJob(
            tenant_id=auth.tenant_id,
            fno_provider=payload.fno_provider,
            job_type=payload.job_type,
            adapter_type=adapter_type,
            request_payload=payload.request_payload,
        )
        session.add(job)
        session.flush()
        session.refresh(job)
        job_id = job.id

    background_tasks.add_task(_run_automation_job, job_id, payload.fno_provider, payload.job_type, payload.request_payload or {})
    logger.info("Dispatched automation job %s [%s/%s] via %s", job_id, payload.fno_provider, payload.job_type, adapter_type)

    with get_session() as session:
        job = session.get(AutomationJob, job_id)
        return AutomationJobRead.model_validate(job)


async def _run_automation_job(
    job_id: uuid.UUID,
    fno_provider: str,
    job_type: str,
    request_payload: dict,
):
    """Execute the automation job in background."""
    adapter = _get_adapter(fno_provider)
    result: dict = {}
    new_status = "completed"

    try:
        if job_type == "coverage_check":
            result = await adapter.check_availability(request_payload.get("address", ""))
        elif job_type == "place_order":
            result = await adapter.place_order(request_payload.get("customer", {}), request_payload.get("plan_id", ""))
        elif job_type == "provision":
            result = await adapter.provision_service(request_payload.get("order_id", ""), request_payload.get("ont_serial"))
        elif job_type == "suspend":
            result = await adapter.suspend_service(request_payload.get("fno_account_id", ""))
        elif job_type == "resume":
            result = await adapter.resume_service(request_payload.get("fno_account_id", ""))
        elif job_type == "fault_report":
            result = await adapter.report_fault(request_payload.get("fno_account_id", ""), request_payload.get("description", ""))
        else:
            result = {"error": f"Unknown job type: {job_type}"}
            new_status = "failed"
    except Exception as exc:
        logger.error("Automation job %s failed: %s", job_id, exc)
        result = {"error": str(exc)}
        new_status = "failed"

    with get_session() as session:
        job = session.get(AutomationJob, job_id)
        if job:
            job.status = new_status
            job.result_payload = result
            job.error_message = result.get("error")
            now = datetime.now(timezone.utc)
            if not job.started_at:
                job.started_at = now
            job.completed_at = now


@router.get("/automation/jobs", response_model=PaginatedResponse)
async def list_automation_jobs(
    auth: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    fno_provider: Optional[str] = None,
):
    with get_session() as session:
        q = select(AutomationJob).where(AutomationJob.tenant_id == auth.tenant_id)
        count_q = select(func.count(AutomationJob.id)).where(AutomationJob.tenant_id == auth.tenant_id)

        if status_filter:
            q = q.where(AutomationJob.status == status_filter)
            count_q = count_q.where(AutomationJob.status == status_filter)
        if fno_provider:
            q = q.where(AutomationJob.fno_provider == fno_provider.lower())
            count_q = count_q.where(AutomationJob.fno_provider == fno_provider.lower())

        total = session.execute(count_q).scalar() or 0
        rows = session.execute(
            q.order_by(AutomationJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return PaginatedResponse(
            items=[AutomationJobRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/automation/jobs/{job_id}", response_model=AutomationJobRead)
async def get_automation_job(
    job_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        job = session.execute(
            select(AutomationJob).where(
                AutomationJob.id == job_id,
                AutomationJob.tenant_id == auth.tenant_id,
            )
        ).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Automation job not found")
        return AutomationJobRead.model_validate(job)


@router.get("/providers")
async def list_fno_providers():
    """Return list of registered FNO providers."""
    return {"providers": FNOFactory.list_providers()}
