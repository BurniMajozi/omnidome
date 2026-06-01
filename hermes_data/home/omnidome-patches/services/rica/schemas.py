"""Pydantic schemas for the RICA Service."""

import uuid
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RICAVerificationCreate(BaseModel):
    customer_id: uuid.UUID
    id_number: str = Field(..., min_length=13, max_length=13)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    verification_type: str = "basic_kyc"


class RICAVerificationUpdate(BaseModel):
    status: Optional[str] = None
    smile_id_job_id: Optional[str] = None
    result_code: Optional[str] = None
    result_text: Optional[str] = None
    image_selfie_url: Optional[str] = None
    image_id_url: Optional[str] = None
    verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class RICAVerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    id_number: str
    first_name: str
    last_name: str
    verification_type: str
    status: str
    smile_id_job_id: Optional[str] = None
    result_code: Optional[str] = None
    result_text: Optional[str] = None
    image_selfie_url: Optional[str] = None
    image_id_url: Optional[str] = None
    verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RICAVerifyRequest(BaseModel):
    customer_id: uuid.UUID
    id_number: str = Field(..., min_length=13, max_length=13)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    verification_type: str = "basic_kyc"
    selfie_image_base64: Optional[str] = None
    id_image_base64: Optional[str] = None


class RICAVerifyResponse(BaseModel):
    job_id: str
    status: str
    result_code: Optional[str] = None
    result_text: Optional[str] = None


class RICALogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    verification_id: uuid.UUID
    action: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int
