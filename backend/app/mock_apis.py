"""
Mock APIs for Context Graph Decision Engine

Simulates external system APIs (CRM, Support, Finance) with realistic data
for 5 test customers. All responses include `retrieved_at` timestamps
to support temporal decision tracing.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class CRMResponse(BaseModel):
    """CRM system response (simulates Salesforce)"""
    customer_name: str
    arr: int = Field(..., description="Annual Recurring Revenue in USD")
    tier: str = Field(..., description="Customer tier (startup, growth, enterprise)")
    industry: str = Field(..., description="Industry vertical")
    contract_start: str = Field(..., description="Contract start date")
    contract_end: str = Field(..., description="Contract end date")
    account_owner: str = Field(..., description="Account owner email")
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when data was retrieved"
    )


class SupportResponse(BaseModel):
    """Support system response (simulates Zendesk)"""
    customer_name: str
    sev1_tickets: int = Field(..., description="Count of SEV-1 (critical) tickets")
    sev2_tickets: int = Field(..., description="Count of SEV-2 (high) tickets")
    sev3_tickets: int = Field(..., description="Count of SEV-3 (medium) tickets")
    total_tickets: int = Field(..., description="Total ticket count")
    satisfaction_score: float = Field(..., description="CSAT score (1-5)")
    avg_resolution_hours: float = Field(..., description="Average resolution time")
    last_ticket_date: Optional[str] = Field(None, description="Date of last ticket")
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when data was retrieved"
    )


class FinanceResponse(BaseModel):
    """Finance system response (simulates Stripe/NetSuite)"""
    customer_name: str
    margin_percent: float = Field(..., description="Gross margin percentage")
    ltv: int = Field(..., description="Lifetime Value in USD")
    payment_status: str = Field(..., description="Payment status (current, overdue, etc.)")
    days_overdue: int = Field(default=0, description="Days payment is overdue")
    last_payment_date: Optional[str] = Field(None, description="Date of last payment")
    total_revenue: int = Field(..., description="Total revenue from customer")
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when data was retrieved"
    )


# =============================================================================
# MOCK DATA - 5 TEST CUSTOMERS
# =============================================================================

MOCK_CRM_DATA: Dict[str, Dict] = {
    "MedTech Corp": {
        "customer_name": "MedTech Corp",
        "arr": 450000,
        "tier": "enterprise",
        "industry": "healthcare",
        "contract_start": "2024-07-01",
        "contract_end": "2026-06-30",
        "account_owner": "john.sales@company.com"
    },
    "HealthTech Inc": {
        "customer_name": "HealthTech Inc",
        "arr": 320000,
        "tier": "enterprise",
        "industry": "healthcare",
        "contract_start": "2025-01-15",
        "contract_end": "2027-01-14",
        "account_owner": "sarah.sales@company.com"
    },
    "BioPharm LLC": {
        "customer_name": "BioPharm LLC",
        "arr": 180000,
        "tier": "growth",
        "industry": "biotech",
        "contract_start": "2025-06-01",
        "contract_end": "2026-05-31",
        "account_owner": "mike.sales@company.com"
    },
    "FinServe Co": {
        "customer_name": "FinServe Co",
        "arr": 620000,
        "tier": "enterprise",
        "industry": "finance",
        "contract_start": "2023-03-01",
        "contract_end": "2026-02-28",
        "account_owner": "john.sales@company.com"
    },
    "TechStartup XYZ": {
        "customer_name": "TechStartup XYZ",
        "arr": 45000,
        "tier": "startup",
        "industry": "tech",
        "contract_start": "2025-11-01",
        "contract_end": "2026-10-31",
        "account_owner": "lisa.sales@company.com"
    }
}

MOCK_SUPPORT_DATA: Dict[str, Dict] = {
    "MedTech Corp": {
        "customer_name": "MedTech Corp",
        "sev1_tickets": 3,
        "sev2_tickets": 7,
        "sev3_tickets": 12,
        "total_tickets": 22,
        "satisfaction_score": 3.2,
        "avg_resolution_hours": 4.5,
        "last_ticket_date": "2026-01-28"
    },
    "HealthTech Inc": {
        "customer_name": "HealthTech Inc",
        "sev1_tickets": 1,
        "sev2_tickets": 3,
        "sev3_tickets": 8,
        "total_tickets": 12,
        "satisfaction_score": 4.1,
        "avg_resolution_hours": 6.2,
        "last_ticket_date": "2026-01-15"
    },
    "BioPharm LLC": {
        "customer_name": "BioPharm LLC",
        "sev1_tickets": 0,
        "sev2_tickets": 2,
        "sev3_tickets": 5,
        "total_tickets": 7,
        "satisfaction_score": 4.5,
        "avg_resolution_hours": 8.0,
        "last_ticket_date": "2025-12-20"
    },
    "FinServe Co": {
        "customer_name": "FinServe Co",
        "sev1_tickets": 2,
        "sev2_tickets": 5,
        "sev3_tickets": 15,
        "total_tickets": 22,
        "satisfaction_score": 3.5,
        "avg_resolution_hours": 3.8,
        "last_ticket_date": "2026-01-30"
    },
    "TechStartup XYZ": {
        "customer_name": "TechStartup XYZ",
        "sev1_tickets": 0,
        "sev2_tickets": 0,
        "sev3_tickets": 2,
        "total_tickets": 2,
        "satisfaction_score": 4.8,
        "avg_resolution_hours": 12.0,
        "last_ticket_date": "2025-12-01"
    }
}

MOCK_FINANCE_DATA: Dict[str, Dict] = {
    "MedTech Corp": {
        "customer_name": "MedTech Corp",
        "margin_percent": 32.0,
        "ltv": 2400000,
        "payment_status": "current",
        "days_overdue": 0,
        "last_payment_date": "2026-01-15",
        "total_revenue": 1350000
    },
    "HealthTech Inc": {
        "customer_name": "HealthTech Inc",
        "margin_percent": 38.0,
        "ltv": 1600000,
        "payment_status": "current",
        "days_overdue": 0,
        "last_payment_date": "2026-01-20",
        "total_revenue": 640000
    },
    "BioPharm LLC": {
        "customer_name": "BioPharm LLC",
        "margin_percent": 42.0,
        "ltv": 900000,
        "payment_status": "current",
        "days_overdue": 0,
        "last_payment_date": "2026-01-01",
        "total_revenue": 180000
    },
    "FinServe Co": {
        "customer_name": "FinServe Co",
        "margin_percent": 28.0,
        "ltv": 3100000,
        "payment_status": "overdue",
        "days_overdue": 15,
        "last_payment_date": "2025-12-01",
        "total_revenue": 1860000
    },
    "TechStartup XYZ": {
        "customer_name": "TechStartup XYZ",
        "margin_percent": 55.0,
        "ltv": 225000,
        "payment_status": "current",
        "days_overdue": 0,
        "last_payment_date": "2025-12-15",
        "total_revenue": 45000
    }
}


# =============================================================================
# ROUTER
# =============================================================================

router = APIRouter(prefix="/api/mock", tags=["Mock APIs"])


def _normalize_customer_name(name: str) -> Optional[str]:
    """
    Normalize customer name for lookup.
    Handles case-insensitivity and common variations.
    """
    name_lower = name.lower().strip()
    
    for key in MOCK_CRM_DATA.keys():
        if key.lower() == name_lower:
            return key
    
    # Try partial matching
    for key in MOCK_CRM_DATA.keys():
        if name_lower in key.lower() or key.lower() in name_lower:
            return key
    
    return None


@router.get("/crm/{customer_name}", response_model=CRMResponse)
async def get_crm_data(customer_name: str) -> CRMResponse:
    """
    Get CRM data for a customer (simulates Salesforce API).
    
    Returns customer profile including ARR, tier, industry, and contract dates.
    All responses include retrieved_at timestamp for temporal tracking.
    """
    normalized = _normalize_customer_name(customer_name)
    
    if not normalized:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_name}' not found in CRM. "
                   f"Available customers: {list(MOCK_CRM_DATA.keys())}"
        )
    
    data = MOCK_CRM_DATA[normalized].copy()
    data["retrieved_at"] = datetime.utcnow()
    
    return CRMResponse(**data)


@router.get("/support/{customer_name}", response_model=SupportResponse)
async def get_support_data(customer_name: str) -> SupportResponse:
    """
    Get support ticket data for a customer (simulates Zendesk API).
    
    Returns ticket counts by severity, CSAT score, and resolution metrics.
    All responses include retrieved_at timestamp for temporal tracking.
    """
    normalized = _normalize_customer_name(customer_name)
    
    if not normalized:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_name}' not found in Support system. "
                   f"Available customers: {list(MOCK_SUPPORT_DATA.keys())}"
        )
    
    data = MOCK_SUPPORT_DATA[normalized].copy()
    data["retrieved_at"] = datetime.utcnow()
    
    return SupportResponse(**data)


@router.get("/finance/{customer_name}", response_model=FinanceResponse)
async def get_finance_data(customer_name: str) -> FinanceResponse:
    """
    Get financial data for a customer (simulates Stripe/NetSuite API).
    
    Returns margin, LTV, payment status, and revenue metrics.
    All responses include retrieved_at timestamp for temporal tracking.
    """
    normalized = _normalize_customer_name(customer_name)
    
    if not normalized:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_name}' not found in Finance system. "
                   f"Available customers: {list(MOCK_FINANCE_DATA.keys())}"
        )
    
    data = MOCK_FINANCE_DATA[normalized].copy()
    data["retrieved_at"] = datetime.utcnow()
    
    return FinanceResponse(**data)


@router.get("/customers")
async def list_customers() -> Dict:
    """
    List all available mock customers.
    
    Useful for testing and discovering available test data.
    """
    return {
        "customers": list(MOCK_CRM_DATA.keys()),
        "count": len(MOCK_CRM_DATA),
        "systems": ["crm", "support", "finance"]
    }


# =============================================================================
# HELPER FUNCTIONS FOR INTERNAL USE
# =============================================================================

async def get_all_customer_data(customer_name: str) -> Dict:
    """
    Get all data for a customer from all mock systems.
    Used by decision engine for parallel data enrichment.
    
    Returns:
        Dict with crm, support, and finance data (or None for each if not found)
    """
    normalized = _normalize_customer_name(customer_name)
    
    result = {
        "crm": None,
        "support": None,
        "finance": None,
        "customer_found": False
    }
    
    if not normalized:
        return result
    
    result["customer_found"] = True
    
    if normalized in MOCK_CRM_DATA:
        data = MOCK_CRM_DATA[normalized].copy()
        data["retrieved_at"] = datetime.utcnow()
        result["crm"] = data
    
    if normalized in MOCK_SUPPORT_DATA:
        data = MOCK_SUPPORT_DATA[normalized].copy()
        data["retrieved_at"] = datetime.utcnow()
        result["support"] = data
    
    if normalized in MOCK_FINANCE_DATA:
        data = MOCK_FINANCE_DATA[normalized].copy()
        data["retrieved_at"] = datetime.utcnow()
        result["finance"] = data
    
    return result
