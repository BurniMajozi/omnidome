"""Pydantic v2 schemas for the Network service."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums (matching SQLAlchemy model enums)
# ---------------------------------------------------------------------------

SERVICE_STATUSES = {"pending", "provisioning", "active", "suspended", "terminated"}
TECHNOLOGY_TYPES = {"gpon", "xgs_pon", "point_to_point", "wireless", "dsl", "lte"}
FNO_PROVIDERS = {"vumatel", "openserve", "metrofibre", "frogfoot", "octotel", "other"}
ORDER_TYPES = {"new_installation", "migration", "speed_change", "cancellation"}
ORDER_STATUSES = {"submitted", "accepted", "scheduled", "in_progress", "completed", "failed", "cancelled"}
FRAMING_PROTOCOLS = {"PPPoE", "IPoE", "PPP"}
SA_PROVINCES = {
    "gauteng", "western_cape", "kwazulu_natal", "eastern_cape",
    "free_state", "mpumalanga", "limpopo", "north_west", "northern_cape",
}


# ---------------------------------------------------------------------------
# Network Service schemas
# ---------------------------------------------------------------------------

class NetworkServiceCreate(BaseModel):
    customer_id: uuid.UUID
    description: Optional[str] = None
    technology: str
    fno_provider: str
    download_speed_mbps: int = Field(ge=1, le=10000)
    upload_speed_mbps: int = Field(ge=1, le=10000)
    speed_profile_name: Optional[str] = None
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: Optional[str] = None
    city: str = Field(min_length=1, max_length=100)
    province: str
    postal_code: str = Field(min_length=4, max_length=10)
    gps_latitude: Optional[str] = None
    gps_longitude: Optional[str] = None
    ont_serial: Optional[str] = None

    @field_validator("technology")
    @classmethod
    def validate_technology(cls, v: str) -> str:
        v = v.lower()
        if v not in TECHNOLOGY_TYPES:
            raise ValueError(f"technology must be one of {TECHNOLOGY_TYPES}")
        return v

    @field_validator("fno_provider")
    @classmethod
    def validate_fno_provider(cls, v: str) -> str:
        v = v.lower()
        if v not in FNO_PROVIDERS:
            raise ValueError(f"fno_provider must be one of {FNO_PROVIDERS}")
        return v

    @field_validator("province")
    @classmethod
    def validate_province(cls, v: str) -> str:
        v = v.lower()
        if v not in SA_PROVINCES:
            raise ValueError(f"province must be one of {SA_PROVINCES}")
        return v


class NetworkServiceUpdate(BaseModel):
    description: Optional[str] = None
    download_speed_mbps: Optional[int] = Field(default=None, ge=1, le=10000)
    upload_speed_mbps: Optional[int] = Field(default=None, ge=1, le=10000)
    speed_profile_name: Optional[str] = None
    ont_serial: Optional[str] = None
    fno_account_id: Optional[str] = None


class NetworkServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    service_reference: str
    description: Optional[str]
    status: str
    technology: str
    fno_provider: str
    download_speed_mbps: int
    upload_speed_mbps: int
    speed_profile_name: Optional[str]
    address_line1: str
    address_line2: Optional[str]
    city: str
    province: str
    postal_code: str
    gps_latitude: Optional[str]
    gps_longitude: Optional[str]
    fno_order_id: Optional[str]
    fno_account_id: Optional[str]
    ont_serial: Optional[str]
    activated_at: Optional[datetime]
    suspended_at: Optional[datetime]
    terminated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# RADIUS schemas
# ---------------------------------------------------------------------------

class RadiusAccountCreate(BaseModel):
    service_id: uuid.UUID
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    framing_protocol: str = "PPPoE"
    profile_name: str = Field(min_length=1, max_length=100)
    mikrotik_rate_limit: Optional[str] = None
    nas_ip_address: Optional[str] = None
    nas_port_id: Optional[str] = None

    @field_validator("framing_protocol")
    @classmethod
    def validate_framing(cls, v: str) -> str:
        if v not in FRAMING_PROTOCOLS:
            raise ValueError(f"framing_protocol must be one of {FRAMING_PROTOCOLS}")
        return v


class RadiusAccountUpdate(BaseModel):
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    profile_name: Optional[str] = None
    mikrotik_rate_limit: Optional[str] = None
    status: Optional[str] = None
    nas_ip_address: Optional[str] = None
    nas_port_id: Optional[str] = None


class RadiusAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID
    username: str
    framing_protocol: str
    status: str
    profile_name: str
    mikrotik_rate_limit: Optional[str]
    nas_ip_address: Optional[str]
    nas_port_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class RadiusSessionInfo(BaseModel):
    """Read-only representation of a live RADIUS session from radacct."""
    username: str
    nas_ip_address: str
    framed_ip_address: Optional[str] = None
    session_id: str
    uptime_seconds: int
    input_octets: int
    output_octets: int
    calling_station_id: Optional[str] = None


# ---------------------------------------------------------------------------
# FNO Order schemas
# ---------------------------------------------------------------------------

class FNOOrderCreate(BaseModel):
    service_id: uuid.UUID
    fno_provider: str
    order_type: str
    scheduled_date: Optional[datetime] = None
    request_payload: Optional[dict[str, Any]] = None

    @field_validator("fno_provider")
    @classmethod
    def validate_fno(cls, v: str) -> str:
        v = v.lower()
        if v not in FNO_PROVIDERS:
            raise ValueError(f"fno_provider must be one of {FNO_PROVIDERS}")
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        v = v.lower()
        if v not in ORDER_TYPES:
            raise ValueError(f"order_type must be one of {ORDER_TYPES}")
        return v


class FNOOrderUpdate(BaseModel):
    status: Optional[str] = None
    fno_reference: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    response_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class FNOOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID
    fno_provider: str
    order_type: str
    status: str
    fno_reference: Optional[str]
    scheduled_date: Optional[datetime]
    completed_date: Optional[datetime]
    request_payload: Optional[dict[str, Any]]
    response_payload: Optional[dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Coverage schemas
# ---------------------------------------------------------------------------

class CoverageCheckRequest(BaseModel):
    address: str = Field(min_length=5, max_length=500)
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    fno_providers: Optional[list[str]] = None  # filter to specific FNOs

    @field_validator("fno_providers")
    @classmethod
    def validate_providers(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            v = [p.lower() for p in v]
            for p in v:
                if p not in FNO_PROVIDERS:
                    raise ValueError(f"Invalid FNO provider: {p}")
        return v


class CoverageResult(BaseModel):
    fno_provider: str
    available: bool
    technology: Optional[str] = None
    max_download_mbps: Optional[int] = None
    area_name: Optional[str] = None
    adapter_type: str = "cache"  # cache / api / browser
    message: Optional[str] = None


class CoverageAreaCreate(BaseModel):
    fno_provider: str
    area_name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    province: str
    postal_codes: Optional[list[str]] = None
    technology: str
    max_download_mbps: int = Field(default=1000, ge=1)
    is_active: bool = True

    @field_validator("fno_provider")
    @classmethod
    def validate_fno(cls, v: str) -> str:
        v = v.lower()
        if v not in FNO_PROVIDERS:
            raise ValueError(f"fno_provider must be one of {FNO_PROVIDERS}")
        return v

    @field_validator("technology")
    @classmethod
    def validate_tech(cls, v: str) -> str:
        v = v.lower()
        if v not in TECHNOLOGY_TYPES:
            raise ValueError(f"technology must be one of {TECHNOLOGY_TYPES}")
        return v

    @field_validator("province")
    @classmethod
    def validate_province(cls, v: str) -> str:
        v = v.lower()
        if v not in SA_PROVINCES:
            raise ValueError(f"province must be one of {SA_PROVINCES}")
        return v


class CoverageAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    fno_provider: str
    area_name: str
    city: str
    province: str
    postal_codes: Optional[list[str]]
    technology: str
    max_download_mbps: int
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Automation Job schemas
# ---------------------------------------------------------------------------

class AutomationJobCreate(BaseModel):
    fno_provider: str
    job_type: str = Field(min_length=1, max_length=50)
    request_payload: Optional[dict[str, Any]] = None

    @field_validator("fno_provider")
    @classmethod
    def validate_fno(cls, v: str) -> str:
        v = v.lower()
        if v not in FNO_PROVIDERS:
            raise ValueError(f"fno_provider must be one of {FNO_PROVIDERS}")
        return v


class AutomationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    fno_provider: str
    job_type: str
    adapter_type: str
    status: str
    request_payload: Optional[dict[str, Any]]
    result_payload: Optional[dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


# ---------------------------------------------------------------------------
# Service management (suspend / reinstate) schemas
# ---------------------------------------------------------------------------

class ServiceSuspendRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class ServiceReinstateRequest(BaseModel):
    reason: Optional[str] = None


class BulkCustomerSuspendRequest(BaseModel):
    """Used by Billing service to suspend all services for a customer."""
    customer_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=255)


class BulkCustomerReinstateRequest(BaseModel):
    """Used by Billing service to reinstate all services for a customer."""
    customer_id: uuid.UUID
    reason: Optional[str] = None


class SpeedChangeRequest(BaseModel):
    download_speed_mbps: int = Field(ge=1, le=10000)
    upload_speed_mbps: int = Field(ge=1, le=10000)
    speed_profile_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Generic pagination wrapper
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
