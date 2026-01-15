from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime, date
import logging

app = FastAPI(title="CoreConnect HR Service", version="0.1.0")

# --- Models ---
class EmployeeBase(BaseModel):
    full_name: str
    job_title: str
    department: str
    hire_date: date

class EmployeeCreate(EmployeeBase):
    employee_id: str

class Employee(EmployeeBase):
    id: uuid.UUID
    employee_id: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True

class PerformanceMetrics(BaseModel):
    employee_id: uuid.UUID
    tickets_resolved: int
    avg_resolution_time: int
    fcr_rate: float
    kpi_score: float
    sentiment_score: float
    attrition_risk: str

# --- IAM Middleware (Stub) ---
async def get_current_tenant_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000000")

# --- Routes ---
@app.get("/")
async def root():
    return {"message": "CoreConnect HR Service is active"}

@app.get("/employees", response_model=List[Employee])
async def list_employees(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return [
        {
            "id": uuid.uuid4(),
            "employee_id": "STF-001",
            "full_name": "Thabo Molefe",
            "job_title": "Support Lead",
            "department": "Support",
            "hire_date": date(2023, 5, 15),
            "status": "ACTIVE",
            "created_at": datetime.now()
        },
        {
            "id": uuid.uuid4(),
            "employee_id": "STF-002",
            "full_name": "Sarah Jenkins",
            "job_title": "Network Technician",
            "department": "Network",
            "hire_date": date(2024, 1, 10),
            "status": "ACTIVE",
            "created_at": datetime.now()
        }
    ]

@app.get("/employees/{emp_id}/performance", response_model=PerformanceMetrics)
async def get_employee_performance(emp_id: uuid.UUID):
    """
    Simulating NLP and Support Hub integration.
    In a real scenario, this would aggregate data from 'tickets' and 'staff_sentiment_logs'.
    """
    return {
        "employee_id": emp_id,
        "tickets_resolved": 145,
        "avg_resolution_time": 42, # minutes
        "fcr_rate": 78.5,
        "kpi_score": 8.5,
        "sentiment_score": 0.82, # Positive
        "attrition_risk": "LOW"
    }

@app.get("/analytics/attrition-risk")
async def get_attrition_risk_overview(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """AI-driven attrition prediction based on sentiment trends"""
    return {
        "total_employees": 25,
        "high_risk_count": 2,
        "medium_risk_count": 5,
        "low_risk_count": 18,
        "primary_attrition_factors": ["High volume of URGENT tickets", "Shift burnout", "Peer feedback sentiment dips"],
        "recommendations": [
            "Initiate retention interview with Support STF-005",
            "Revise shift rotation for NOC team",
            "Schedule training for 'Stress Management' in peak periods"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
