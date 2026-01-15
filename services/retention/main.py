"""
OmniDome Retention Service
Handles churn prediction, retention analytics, and customer risk scoring.
"""

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
from enum import Enum
import random

app = FastAPI(
    title="OmniDome Retention Service",
    description="AI-powered churn prediction and customer retention management",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Enums ---
class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOYAL = "loyal"

class ChurnReason(str, Enum):
    PRICE_SENSITIVITY = "price_sensitivity"
    SERVICE_ISSUES = "service_issues"
    COMPETITOR_OFFER = "competitor_offer"
    RELOCATION = "relocation"
    NO_LONGER_NEEDED = "no_longer_needed"
    PAYMENT_ISSUES = "payment_issues"

class RetentionStatus(str, Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    OFFER_SENT = "offer_sent"
    SAVED = "saved"
    CHURNED = "churned"
    ESCALATED = "escalated"

# --- Models ---
class ChurnPrediction(BaseModel):
    customer_id: uuid.UUID
    account_number: str
    customer_name: str
    segment: str
    risk_score: float = Field(..., ge=0, le=100, description="Churn probability 0-100%")
    risk_level: RiskLevel
    primary_reason: ChurnReason
    secondary_reasons: List[ChurnReason] = []
    tenure_months: int
    lifetime_value: float
    last_interaction: datetime
    prediction_date: datetime
    confidence_score: float = Field(..., ge=0, le=1, description="Model confidence 0-1")

class RetentionCase(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    account_number: str
    customer_name: str
    risk_score: float
    risk_level: RiskLevel
    status: RetentionStatus
    assigned_to: Optional[str] = None
    churn_reason: ChurnReason
    recommended_action: str
    notes: List[str] = []
    created_at: datetime
    last_updated: datetime

class RetentionCampaign(BaseModel):
    id: uuid.UUID
    name: str
    target_segment: str
    discount_percentage: Optional[float] = None
    customers_targeted: int
    customers_saved: int
    revenue_preserved: float
    roi_percentage: float
    start_date: datetime
    end_date: Optional[datetime] = None
    is_active: bool

class ChurnMetrics(BaseModel):
    period: str
    churn_rate: float
    prediction_accuracy: float
    at_risk_customers: int
    customers_saved: int
    revenue_preserved: float
    retention_rate: float
    avg_customer_lifetime_value: float

class RiskSegmentSummary(BaseModel):
    segment: RiskLevel
    customer_count: int
    percentage: float
    avg_risk_score: float
    primary_reasons: Dict[str, int]

# --- Mock Data Helpers ---
def generate_mock_predictions(count: int = 50) -> List[ChurnPrediction]:
    segments = ["Enterprise", "Business", "Premium", "Standard", "Basic"]
    names = [
        "Thabo Mokoena", "Lerato Mbeki", "Johan Pretorius", "Nomvula Dlamini",
        "Sipho Nkosi", "Sarah van der Merwe", "David Smith", "Lindiwe Zulu",
        "Peter Botha", "Grace Molefe", "Marcus du Plessis", "Andile Khumalo"
    ]
    
    predictions = []
    for i in range(count):
        risk_score = random.uniform(50, 98) if i < 10 else random.uniform(20, 70)
        risk_level = (
            RiskLevel.CRITICAL if risk_score >= 90 else
            RiskLevel.HIGH if risk_score >= 70 else
            RiskLevel.MEDIUM if risk_score >= 50 else
            RiskLevel.LOW if risk_score >= 30 else
            RiskLevel.LOYAL
        )
        
        predictions.append(ChurnPrediction(
            customer_id=uuid.uuid4(),
            account_number=f"ACC-{random.randint(10000, 99999)}",
            customer_name=random.choice(names),
            segment=random.choice(segments),
            risk_score=round(risk_score, 1),
            risk_level=risk_level,
            primary_reason=random.choice(list(ChurnReason)),
            secondary_reasons=random.sample(list(ChurnReason), k=random.randint(0, 2)),
            tenure_months=random.randint(1, 60),
            lifetime_value=random.uniform(2000, 50000),
            last_interaction=datetime.now() - timedelta(days=random.randint(1, 30)),
            prediction_date=datetime.now(),
            confidence_score=round(random.uniform(0.75, 0.95), 2)
        ))
    
    return sorted(predictions, key=lambda x: x.risk_score, reverse=True)

# --- Tenant Context (Stub) ---
async def get_current_tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {
        "service": "OmniDome Retention Service",
        "version": "1.0.0",
        "status": "active",
        "features": [
            "Churn Prediction",
            "Risk Scoring",
            "Retention Campaign Management",
            "Customer Lifetime Value Analysis"
        ]
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/metrics", response_model=ChurnMetrics)
async def get_churn_metrics(
    period: str = Query("monthly", description="Metrics period: weekly, monthly, quarterly"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get aggregated churn and retention metrics"""
    return ChurnMetrics(
        period=period,
        churn_rate=2.1,
        prediction_accuracy=87.3,
        at_risk_customers=847,
        customers_saved=343,
        revenue_preserved=2100000.00,
        retention_rate=97.9,
        avg_customer_lifetime_value=18500.00
    )

@app.get("/predictions", response_model=List[ChurnPrediction])
async def get_churn_predictions(
    risk_level: Optional[RiskLevel] = None,
    segment: Optional[str] = None,
    min_risk_score: float = Query(0, ge=0, le=100),
    limit: int = Query(50, le=500),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get AI-powered churn predictions for customers"""
    predictions = generate_mock_predictions(limit)
    
    if risk_level:
        predictions = [p for p in predictions if p.risk_level == risk_level]
    if segment:
        predictions = [p for p in predictions if p.segment.lower() == segment.lower()]
    if min_risk_score > 0:
        predictions = [p for p in predictions if p.risk_score >= min_risk_score]
    
    return predictions[:limit]

@app.get("/predictions/{customer_id}", response_model=ChurnPrediction)
async def get_customer_prediction(
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get detailed churn prediction for a specific customer"""
    # Mock single customer prediction
    return ChurnPrediction(
        customer_id=customer_id,
        account_number=f"ACC-{random.randint(10000, 99999)}",
        customer_name="Thabo Mokoena",
        segment="Premium",
        risk_score=87.5,
        risk_level=RiskLevel.HIGH,
        primary_reason=ChurnReason.PRICE_SENSITIVITY,
        secondary_reasons=[ChurnReason.SERVICE_ISSUES],
        tenure_months=14,
        lifetime_value=24800.00,
        last_interaction=datetime.now() - timedelta(days=7),
        prediction_date=datetime.now(),
        confidence_score=0.89
    )

@app.get("/risk-segments", response_model=List[RiskSegmentSummary])
async def get_risk_segments(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Get customer distribution by risk segment"""
    return [
        RiskSegmentSummary(
            segment=RiskLevel.CRITICAL,
            customer_count=124,
            percentage=0.5,
            avg_risk_score=93.2,
            primary_reasons={"price_sensitivity": 45, "service_issues": 35, "competitor_offer": 44}
        ),
        RiskSegmentSummary(
            segment=RiskLevel.HIGH,
            customer_count=723,
            percentage=2.9,
            avg_risk_score=78.4,
            primary_reasons={"price_sensitivity": 280, "service_issues": 210, "competitor_offer": 233}
        ),
        RiskSegmentSummary(
            segment=RiskLevel.MEDIUM,
            customer_count=2134,
            percentage=8.6,
            avg_risk_score=58.7,
            primary_reasons={"service_issues": 640, "no_longer_needed": 534, "price_sensitivity": 960}
        ),
        RiskSegmentSummary(
            segment=RiskLevel.LOW,
            customer_count=8521,
            percentage=34.2,
            avg_risk_score=35.2,
            primary_reasons={"no_engagement": 2556, "service_issues": 1704, "relocation": 4261}
        ),
        RiskSegmentSummary(
            segment=RiskLevel.LOYAL,
            customer_count=13345,
            percentage=53.6,
            avg_risk_score=12.8,
            primary_reasons={}
        )
    ]

@app.get("/cases", response_model=List[RetentionCase])
async def get_retention_cases(
    status: Optional[RetentionStatus] = None,
    risk_level: Optional[RiskLevel] = None,
    limit: int = Query(50, le=200),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get active retention cases"""
    cases = [
        RetentionCase(
            id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            account_number="ACC-78421",
            customer_name="Lerato Mbeki",
            risk_score=94.2,
            risk_level=RiskLevel.CRITICAL,
            status=RetentionStatus.CONTACTED,
            assigned_to="Retention Team",
            churn_reason=ChurnReason.SERVICE_ISSUES,
            recommended_action="Offer 20% discount + personal apology call",
            notes=["Customer reported slow speeds", "Field tech dispatched"],
            created_at=datetime.now() - timedelta(days=2),
            last_updated=datetime.now()
        ),
        RetentionCase(
            id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            account_number="ACC-65892",
            customer_name="Johan Pretorius",
            risk_score=87.1,
            risk_level=RiskLevel.HIGH,
            status=RetentionStatus.OFFER_SENT,
            assigned_to="Sales Rep",
            churn_reason=ChurnReason.PRICE_SENSITIVITY,
            recommended_action="Offer loyalty discount or upgrade bundle",
            notes=["Customer comparing MTN prices"],
            created_at=datetime.now() - timedelta(days=1),
            last_updated=datetime.now() - timedelta(hours=4)
        )
    ]
    
    if status:
        cases = [c for c in cases if c.status == status]
    if risk_level:
        cases = [c for c in cases if c.risk_level == risk_level]
    
    return cases[:limit]

@app.post("/cases/{case_id}/action")
async def take_retention_action(
    case_id: uuid.UUID,
    action: str,
    notes: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Record a retention action taken on a case"""
    return {
        "case_id": case_id,
        "action_taken": action,
        "notes": notes,
        "timestamp": datetime.now().isoformat(),
        "status": "recorded"
    }

@app.get("/campaigns", response_model=List[RetentionCampaign])
async def get_retention_campaigns(
    is_active: Optional[bool] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get retention campaigns and their performance"""
    campaigns = [
        RetentionCampaign(
            id=uuid.uuid4(),
            name="Win-Back Email Q1",
            target_segment="Churned (30-60 days)",
            discount_percentage=15.0,
            customers_targeted=500,
            customers_saved=142,
            revenue_preserved=426000.00,
            roi_percentage=312.0,
            start_date=datetime.now() - timedelta(days=30),
            end_date=None,
            is_active=True
        ),
        RetentionCampaign(
            id=uuid.uuid4(),
            name="Loyalty Appreciation",
            target_segment="High-Value At-Risk",
            discount_percentage=20.0,
            customers_targeted=200,
            customers_saved=89,
            revenue_preserved=712000.00,
            roi_percentage=156.0,
            start_date=datetime.now() - timedelta(days=45),
            end_date=None,
            is_active=True
        ),
        RetentionCampaign(
            id=uuid.uuid4(),
            name="Personal Outreach",
            target_segment="Enterprise Critical",
            discount_percentage=None,
            customers_targeted=50,
            customers_saved=67,
            revenue_preserved=832000.00,
            roi_percentage=248.0,
            start_date=datetime.now() - timedelta(days=60),
            end_date=datetime.now() - timedelta(days=5),
            is_active=False
        )
    ]
    
    if is_active is not None:
        campaigns = [c for c in campaigns if c.is_active == is_active]
    
    return campaigns

@app.get("/analytics/churn-trend")
async def get_churn_trend(
    months: int = Query(6, ge=1, le=24),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get historical churn rate trend"""
    base_date = datetime.now()
    trend = []
    churn_rate = 3.5  # Starting rate
    
    for i in range(months, 0, -1):
        month_date = base_date - timedelta(days=i * 30)
        # Simulate improving churn rate
        churn_rate = max(2.0, churn_rate - random.uniform(0.05, 0.25))
        
        trend.append({
            "month": month_date.strftime("%b %Y"),
            "churn_rate": round(churn_rate, 2),
            "predicted_rate": round(churn_rate + random.uniform(-0.2, 0.3), 2),
            "customers_churned": int(24847 * churn_rate / 100),
            "customers_saved": random.randint(200, 400)
        })
    
    return {"period": f"Last {months} months", "data": trend}

@app.get("/analytics/churn-reasons")
async def get_churn_reasons_breakdown(
    period: str = Query("monthly", description="weekly, monthly, quarterly"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Get breakdown of churn reasons"""
    return {
        "period": period,
        "total_churned": 521,
        "reasons": [
            {"reason": "Price Sensitivity", "count": 167, "percentage": 32.1},
            {"reason": "Service Issues", "count": 130, "percentage": 25.0},
            {"reason": "Competitor Offers", "count": 94, "percentage": 18.0},
            {"reason": "Relocation", "count": 68, "percentage": 13.0},
            {"reason": "No Longer Needed", "count": 62, "percentage": 11.9}
        ]
    }

@app.get("/analytics/clv-by-segment")
async def get_clv_by_segment(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Get Customer Lifetime Value by segment"""
    return {
        "segments": [
            {"segment": "Enterprise", "clv": 48500, "retention_rate": 94.2, "customer_count": 1247},
            {"segment": "Business", "clv": 24800, "retention_rate": 91.5, "customer_count": 3892},
            {"segment": "Premium", "clv": 12400, "retention_rate": 88.7, "customer_count": 6521},
            {"segment": "Standard", "clv": 6200, "retention_rate": 85.3, "customer_count": 8745},
            {"segment": "Basic", "clv": 2400, "retention_rate": 79.8, "customer_count": 4442}
        ],
        "avg_clv": 18500,
        "total_lifetime_value": 461245000
    }

@app.post("/predict/batch")
async def trigger_batch_prediction(
    segment: Optional[str] = None,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Trigger batch churn prediction for all/segment customers"""
    return {
        "job_id": str(uuid.uuid4()),
        "status": "queued",
        "segment": segment or "all",
        "estimated_customers": 24847 if not segment else random.randint(1000, 5000),
        "estimated_completion": (datetime.now() + timedelta(minutes=15)).isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012)
