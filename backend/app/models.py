"""
Pydantic Models for Context Graph Decision Engine

Defines complete type-safe data models for decision trace capture,
including all sub-components for evidence, policy, and precedent tracking.
"""
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class DecisionType(str, Enum):
    """Types of decisions that can be captured"""
    DISCOUNT_APPROVAL = "discount_approval"
    CREDIT_EXTENSION = "credit_extension"
    REFUND_REQUEST = "refund_request"
    CONTRACT_EXCEPTION = "contract_exception"
    PAYMENT_TERMS = "payment_terms"
    OTHER = "other"


class DecisionOutcome(str, Enum):
    """Possible outcomes of a decision"""
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"  # Approved but with changes (e.g., 15% instead of 18%)
    ESCALATED = "escalated"
    PENDING = "pending"


# =============================================================================
# INPUT MODELS
# =============================================================================

class EmailIngestionRequest(BaseModel):
    """
    Input model for the /decision/ingest endpoint.
    
    Supports two modes:
    1. Gmail Mode: Provide gmail_message_id to fetch from Gmail API
    2. Manual Mode: Provide email_thread text directly (for copy-paste)
    
    Example:
        {
            "email_thread": "From: john@company.com\\nTo: jane@company.com\\n...",
            "customer_name": "MedTech Corp"
        }
    """
    # Gmail mode - fetch from API
    gmail_message_id: Optional[str] = Field(
        default=None,
        description="Gmail message ID to fetch and process"
    )
    gmail_thread_id: Optional[str] = Field(
        default=None,
        description="Gmail thread ID to fetch entire conversation"
    )
    
    # Manual mode - paste text directly
    email_thread: Optional[str] = Field(
        default=None,
        description="Raw email thread text (for manual paste mode)"
    )
    
    # Required context
    customer_name: str = Field(
        ...,
        description="Name of the customer the decision relates to",
        min_length=1,
        max_length=200
    )
    
    # Optional context
    decision_type: DecisionType = Field(
        default=DecisionType.DISCOUNT_APPROVAL,
        description="Type of decision being captured"
    )
    
    @field_validator('customer_name')
    @classmethod
    def validate_customer_name(cls, v: str) -> str:
        """Strip whitespace and validate non-empty"""
        v = v.strip()
        if not v:
            raise ValueError("customer_name cannot be empty")
        return v
    
    def model_post_init(self, __context: Any) -> None:
        """Validate that at least one input mode is provided"""
        if not self.gmail_message_id and not self.gmail_thread_id and not self.email_thread:
            raise ValueError(
                "Must provide either gmail_message_id, gmail_thread_id, or email_thread"
            )


# =============================================================================
# DECISION TRACE SUB-COMPONENTS
# =============================================================================

class DecisionRequest(BaseModel):
    """
    Captures what was requested and by whom.
    
    This is the "ask" - what did someone want to happen?
    """
    customer: str = Field(..., description="Customer name")
    requested_action: str = Field(
        ..., 
        description="What was requested (e.g., '18% discount')"
    )
    requestor_email: Optional[EmailStr] = Field(
        default=None,
        description="Email of person who made the request"
    )
    requestor_name: Optional[str] = Field(
        default=None,
        description="Name of person who made the request"
    )
    requested_at: Optional[datetime] = Field(
        default=None,
        description="When the request was made"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Why this was requested (justification)"
    )


class DecisionOutcomeData(BaseModel):
    """
    Captures the actual decision made.
    
    This is the "response" - what was actually decided?
    """
    outcome: DecisionOutcome = Field(
        ...,
        description="The decision outcome (approved, rejected, modified)"
    )
    final_action: str = Field(
        ...,
        description="The final action taken (e.g., '15% discount')"
    )
    decision_maker_email: Optional[EmailStr] = Field(
        default=None,
        description="Email of person who made the decision"
    )
    decision_maker_name: Optional[str] = Field(
        default=None,
        description="Name of person who made the decision"
    )
    decided_at: Optional[datetime] = Field(
        default=None,
        description="When the decision was made"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Explanation for the decision"
    )


class Evidence(BaseModel):
    """
    A single piece of evidence captured at decision time.
    
    CRITICAL: The captured_at timestamp records when this data was retrieved,
    enabling temporal queries ("What was their ARR when we approved this?")
    """
    source: str = Field(
        ...,
        description="System source (e.g., 'salesforce', 'zendesk', 'stripe')"
    )
    field: str = Field(
        ...,
        description="The specific data field (e.g., 'arr', 'sev1_tickets')"
    )
    value: Union[str, int, float, bool, None] = Field(
        ...,
        description="The captured value at decision time"
    )
    captured_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when this evidence was captured"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "source": "salesforce",
                "field": "arr",
                "value": 450000,
                "captured_at": "2026-01-31T16:30:00Z"
            }
        }


class PolicyInfo(BaseModel):
    """
    Policy version that was active at decision time.
    
    Enables queries like: "Which policy version was in effect?"
    and "Did the policy change after this decision?"
    """
    version: str = Field(..., description="Policy version identifier")
    effective_from: datetime = Field(
        ...,
        description="When this policy version became effective"
    )
    effective_until: Optional[datetime] = Field(
        default=None,
        description="When this policy version was superseded (None if current)"
    )
    rules: Dict[str, Any] = Field(
        default_factory=dict,
        description="Policy rules that were evaluated"
    )
    exception_made: bool = Field(
        default=False,
        description="Whether this decision required a policy exception"
    )


class Precedent(BaseModel):
    """
    A similar past decision used as precedent.
    
    Enables queries like: "What similar decisions have we made?"
    """
    decision_id: str = Field(..., description="ID of the precedent decision")
    customer: str = Field(..., description="Customer from precedent case")
    outcome: str = Field(..., description="What was decided in precedent")
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How similar this precedent is (0-1)"
    )
    timestamp: datetime = Field(..., description="When precedent decision was made")
    why_similar: Optional[str] = Field(
        default=None,
        description="Explanation of why this is considered similar"
    )


class PolicyException(BaseModel):
    """
    Records a deviation from standard policy.
    
    Enables queries like: "Show all policy exceptions" or
    "What's our exception rate for healthcare customers?"
    """
    exception_type: str = Field(
        ...,
        description="Type of exception (e.g., 'exceeds_standard_limit')"
    )
    description: str = Field(
        ...,
        description="Human-readable description of the exception"
    )
    policy_limit: str = Field(
        ...,
        description="What the policy limit was"
    )
    actual_value: str = Field(
        ...,
        description="What was actually approved"
    )
    deviation: str = Field(
        ...,
        description="The deviation from policy (e.g., '5%')"
    )
    approved_by: Optional[str] = Field(
        default=None,
        description="Who had authority to approve this exception"
    )


# =============================================================================
# MAIN DECISION TRACE MODEL
# =============================================================================

class DecisionTrace(BaseModel):
    """
    The complete immutable decision trace.
    
    This is the CORE data structure of the system. Once created, a decision
    trace is NEVER modified. If corrections are needed, a new trace is created
    that references the original.
    
    Example structure:
    ```json
    {
        "decision_id": "dec_abc123",
        "timestamp": "2026-01-31T16:30:00Z",
        "decision_type": "discount_approval",
        "request": { ... },
        "decision": { ... },
        "evidence": [ ... ],
        "policy": { ... },
        "precedents": [ ... ],
        "exceptions": [ ... ]
    }
    ```
    """
    # Identity
    decision_id: str = Field(
        default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}",
        description="Unique decision identifier"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this trace was created"
    )
    decision_type: DecisionType = Field(
        ...,
        description="Type of decision captured"
    )
    
    # Core decision data
    request: DecisionRequest = Field(
        ...,
        description="What was requested"
    )
    decision: DecisionOutcomeData = Field(
        ...,
        description="What was decided"
    )
    
    # Context captured at decision time
    evidence: List[Evidence] = Field(
        default_factory=list,
        description="Evidence captured at decision moment"
    )
    
    # Policy context
    policy: Optional[PolicyInfo] = Field(
        default=None,
        description="Policy version evaluated against"
    )
    
    # Related decisions
    precedents: List[Precedent] = Field(
        default_factory=list,
        description="Similar past decisions considered"
    )
    
    # Exceptions
    exceptions: List[PolicyException] = Field(
        default_factory=list,
        description="Policy exceptions made"
    )
    
    # Lineage (for corrections/amendments)
    corrects_decision: Optional[str] = Field(
        default=None,
        description="If this is a correction, ID of decision being corrected"
    )
    
    # Metadata
    source: str = Field(
        default="gmail",
        description="Source of ingestion (gmail, manual, api)"
    )
    raw_email_text: Optional[str] = Field(
        default=None,
        description="Original email text for audit purposes"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "decision_id": "dec_abc123def4",
                "timestamp": "2026-01-31T16:30:00Z",
                "decision_type": "discount_approval",
                "request": {
                    "customer": "MedTech Corp",
                    "requested_action": "18% discount",
                    "requestor_email": "john.sales@company.com",
                    "requested_at": "2026-01-31T16:25:00Z",
                    "reason": "Customer has 3 SEV-1 incidents, threatening churn"
                },
                "decision": {
                    "outcome": "modified",
                    "final_action": "15% discount",
                    "decision_maker_email": "jane.manager@company.com",
                    "decided_at": "2026-01-31T16:30:00Z",
                    "reasoning": "18% too high given margin. Similar to HealthTech Inc."
                },
                "evidence": [
                    {"source": "salesforce", "field": "arr", "value": 450000}
                ],
                "exceptions": [
                    {
                        "exception_type": "exceeds_standard_limit",
                        "description": "Discount exceeds 10% standard limit",
                        "policy_limit": "10%",
                        "actual_value": "15%",
                        "deviation": "5%"
                    }
                ]
            }
        }


# =============================================================================
# API RESPONSE MODELS
# =============================================================================

class HealthCheckResponse(BaseModel):
    """Health check endpoint response"""
    status: str = Field(..., description="Overall health status")
    gmail: str = Field(default="not_checked", description="Gmail connection status")
    gemini: str = Field(default="not_checked", description="Gemini API status")
    mock_apis: str = Field(default="available", description="Mock APIs status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Health check timestamp"
    )


class SearchResult(BaseModel):
    """Gmail search result item"""
    id: str = Field(..., description="Message ID")
    thread_id: str = Field(..., description="Thread ID")
    subject: Optional[str] = Field(default=None, description="Email subject")
    sender: Optional[str] = Field(default=None, description="Sender email")
    date: Optional[str] = Field(default=None, description="Email date")
    snippet: Optional[str] = Field(default=None, description="Email preview")


class EmailMessage(BaseModel):
    """Parsed email message"""
    id: str = Field(..., description="Message ID")
    thread_id: str = Field(..., description="Thread ID")
    subject: Optional[str] = Field(default=None, description="Email subject")
    sender: Optional[str] = Field(default=None, description="From address")
    recipients: List[str] = Field(default_factory=list, description="To addresses")
    date: Optional[datetime] = Field(default=None, description="Email date")
    body: Optional[str] = Field(default=None, description="Email body text")
    labels: List[str] = Field(default_factory=list, description="Gmail labels")


class PolicyVersionResponse(BaseModel):
    """Policy version information for API response"""
    version: str
    effective_from: datetime
    effective_until: Optional[datetime] = None
    is_current: bool = False
    rules: Dict[str, Any]


class APIError(BaseModel):
    """Standard API error response"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details"
    )
