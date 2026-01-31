"""
Pydantic Models for the Sales Application
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class DecisionType(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REVIEW = "review"


class EmailMessage(BaseModel):
    """Email message model"""
    id: Optional[str] = None
    subject: str
    body: str
    sender: EmailStr
    recipients: List[EmailStr]
    timestamp: Optional[datetime] = None


class Policy(BaseModel):
    """Policy model for the policy store"""
    id: Optional[str] = None
    name: str
    description: str
    rules: dict
    status: PolicyStatus = PolicyStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Decision(BaseModel):
    """Decision model from the decision engine"""
    id: Optional[str] = None
    policy_id: str
    input_data: dict
    decision: DecisionType
    reasoning: str
    confidence: float
    timestamp: Optional[datetime] = None


class APIResponse(BaseModel):
    """Standard API response model"""
    success: bool
    message: str
    data: Optional[dict] = None
