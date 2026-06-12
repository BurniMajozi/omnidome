from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


AGENT_SKILLS: dict[str, list[dict[str, str]]] = {
    "customer_facing": [
        {"id": "customer_support", "name": "Customer support", "description": "Balances, invoices, coverage checks, and support tickets."},
        {"id": "customer_360", "name": "Customer 360", "description": "Read customer relationship, billing, service, and support context."},
    ],
    "retention": [
        {"id": "churn_risk", "name": "Churn risk", "description": "Analyze churn risk and retention cases."},
        {"id": "retention_action", "name": "Retention action", "description": "Suggest and record retention interventions."},
    ],
    "provisioning": [
        {"id": "coverage", "name": "Coverage and provisioning", "description": "Check coverage and coordinate customer provisioning."},
    ],
    "executive": [
        {"id": "executive_briefing", "name": "Executive briefing", "description": "Summarize operational, revenue, and service performance."},
    ],
    "support": [
        {"id": "diagnostics", "name": "Support diagnostics", "description": "Use CRM, support, network, and call center context to troubleshoot."},
    ],
}


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    protocol_version: str = "a2a-0.1"
    skills: list[dict[str, str]]
    default_input_modes: list[str] = Field(default_factory=lambda: ["text/plain", "application/json"])
    default_output_modes: list[str] = Field(default_factory=lambda: ["text/plain", "application/json", "text/event-stream"])


class A2AMessage(BaseModel):
    agent_type: str = Field("support")
    message: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[uuid.UUID] = None


class AGUIRunRequest(A2AMessage):
    stream_tokens: bool = True


class AGUIEvent(BaseModel):
    type: Literal[
        "RUN_STARTED",
        "TEXT_MESSAGE_CONTENT",
        "TOOL_CALL_START",
        "TOOL_CALL_RESULT",
        "TOOL_CALL_END",
        "MEMORY_WRITE",
        "RUN_FINISHED",
        "RUN_ERROR",
    ]
    run_id: uuid.UUID
    tenant_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)


SAFE_A2UI_COMPONENTS = {
    "Badge",
    "Button",
    "Card",
    "CheckBox",
    "Column",
    "DateTimeInput",
    "Divider",
    "Form",
    "Input",
    "List",
    "Row",
    "Select",
    "Table",
    "Tabs",
    "Text",
    "TextArea",
}


class A2UIComponent(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    component: dict[str, Any]

    def component_name(self) -> str:
        return next(iter(self.component.keys()), "")


class A2UIPayload(BaseModel):
    surface_id: str = Field("default", max_length=80)
    root: str
    components: list[A2UIComponent]
    data: dict[str, Any] = Field(default_factory=dict)

    def validate_safe(self) -> None:
        ids = {component.id for component in self.components}
        if self.root not in ids:
            raise ValueError("root component must exist in components")
        for component in self.components:
            if component.component_name() not in SAFE_A2UI_COMPONENTS:
                raise ValueError(f"component not allowed: {component.component_name()}")


class UCPLineItem(BaseModel):
    item_id: str
    label: str
    quantity: int = Field(..., ge=1)
    unit_amount: float = Field(..., ge=0)
    currency: str = "ZAR"


class UCPCheckoutCreateRequest(BaseModel):
    merchant: str
    purpose: str
    line_items: list[UCPLineItem] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(sum(item.quantity * item.unit_amount for item in self.line_items), 2)


class UCPCheckoutSession(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    status: Literal["created", "requires_approval", "completed", "cancelled"] = "created"
    currency: str = "ZAR"
    total: float
    merchant: str
    purpose: str
    line_items: list[UCPLineItem]
    payment_mandate_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentMandateCreate(BaseModel):
    natural_language_description: str
    merchants: list[str] = Field(default_factory=list)
    max_amount: float = Field(..., ge=0)
    currency: str = "ZAR"
    expires_in_minutes: int = Field(60, ge=1, le=1440)
    requires_user_confirmation: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentMandate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    natural_language_description: str
    merchants: list[str]
    max_amount: float
    currency: str
    expires_at: datetime
    requires_user_confirmation: bool
    signed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_create(cls, body: IntentMandateCreate) -> "IntentMandate":
        return cls(
            natural_language_description=body.natural_language_description,
            merchants=body.merchants,
            max_amount=body.max_amount,
            currency=body.currency,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=body.expires_in_minutes),
            requires_user_confirmation=body.requires_user_confirmation,
            metadata=body.metadata,
        )


class PaymentMandateCreate(BaseModel):
    intent_mandate_id: uuid.UUID
    payment_details_id: str
    merchant_agent: str
    amount: float = Field(..., ge=0)
    currency: str = "ZAR"
    label: str
    signed_authorization: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentMandate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    intent_mandate_id: uuid.UUID
    payment_details_id: str
    merchant_agent: str
    amount: float
    currency: str
    label: str
    signed_authorization: Optional[str] = None
    status: Literal["pending_signature", "signed"] = "pending_signature"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentReceiptCreate(BaseModel):
    payment_mandate_id: uuid.UUID
    payment_id: str
    amount: float
    currency: str = "ZAR"
    merchant_confirmation_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentReceipt(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    payment_mandate_id: uuid.UUID
    payment_id: str
    amount: float
    currency: str
    merchant_confirmation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

