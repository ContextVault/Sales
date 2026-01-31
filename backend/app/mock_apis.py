"""
Mock APIs for Testing and Development
"""
from fastapi import APIRouter
from typing import List, Optional
from datetime import datetime
import random

from .models import EmailMessage, Policy, Decision, DecisionType, PolicyStatus

router = APIRouter(prefix="/mock", tags=["Mock APIs"])


# Mock data storage
_mock_emails: List[EmailMessage] = []
_mock_policies: List[Policy] = []
_mock_decisions: List[Decision] = []


@router.get("/emails", response_model=List[EmailMessage])
async def get_mock_emails():
    """Get all mock emails"""
    return _mock_emails


@router.post("/emails", response_model=EmailMessage)
async def create_mock_email(email: EmailMessage):
    """Create a mock email"""
    email.id = f"mock_{len(_mock_emails) + 1}"
    email.timestamp = datetime.utcnow()
    _mock_emails.append(email)
    return email


@router.get("/policies", response_model=List[Policy])
async def get_mock_policies():
    """Get all mock policies"""
    return _mock_policies


@router.post("/policies", response_model=Policy)
async def create_mock_policy(policy: Policy):
    """Create a mock policy"""
    policy.id = f"policy_{len(_mock_policies) + 1}"
    policy.created_at = datetime.utcnow()
    policy.updated_at = datetime.utcnow()
    _mock_policies.append(policy)
    return policy


@router.post("/decisions/simulate", response_model=Decision)
async def simulate_decision(policy_id: str, input_data: dict):
    """Simulate a decision for testing"""
    decision = Decision(
        id=f"decision_{len(_mock_decisions) + 1}",
        policy_id=policy_id,
        input_data=input_data,
        decision=random.choice(list(DecisionType)),
        reasoning="Mock decision for testing purposes",
        confidence=random.uniform(0.5, 1.0),
        timestamp=datetime.utcnow()
    )
    _mock_decisions.append(decision)
    return decision


@router.delete("/reset")
async def reset_mock_data():
    """Reset all mock data"""
    global _mock_emails, _mock_policies, _mock_decisions
    _mock_emails = []
    _mock_policies = []
    _mock_decisions = []
    return {"message": "Mock data reset successfully"}
