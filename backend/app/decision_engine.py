"""
Decision Engine - Core Decision Trace Construction

Orchestrates the complete decision trace construction process:
1. Fetch email content (Gmail API or manual input)
2. Extract structured decision data (Gemini LLM)
3. Enrich with context from CRM/Support/Finance APIs
4. Get applicable policy version
5. Detect policy exceptions
6. Construct immutable DecisionTrace
"""
import asyncio
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import (
    DecisionTrace,
    DecisionRequest,
    DecisionOutcomeData,
    Evidence,
    PolicyInfo,
    PolicyException,
    DecisionType,
    DecisionOutcome,
    EmailIngestionRequest,
)
from .gmail_service import gmail_service
from .gemini_service import gemini_service, extract_decision_from_email
from .policy_store import policy_store
from .mock_apis import get_all_customer_data
from .graph_operations import find_precedents

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Core engine for constructing decision traces.
    
    Orchestrates the complete flow from email ingestion to
    immutable decision trace creation.
    """
    
    def __init__(self):
        """Initialize decision engine."""
        self._decisions: Dict[str, DecisionTrace] = {}
        logger.info("DecisionEngine initialized")
    
    async def construct_decision_trace(
        self,
        request: EmailIngestionRequest
    ) -> DecisionTrace:
        """
        Main entry point for constructing a decision trace.
        
        Handles both Gmail mode and manual paste mode based on request.
        
        Args:
            request: EmailIngestionRequest with either gmail_message_id,
                    gmail_thread_id, or email_thread text
                    
        Returns:
            Complete DecisionTrace with all enrichment
        """
        logger.info(f"Starting decision trace construction for {request.customer_name}")
        
        # Step 1: Get email text
        if request.email_thread:
            # Manual paste mode
            email_text = request.email_thread
            source = "manual"
        elif request.gmail_thread_id:
            # Gmail thread mode
            thread = await gmail_service.get_thread(request.gmail_thread_id)
            if not thread:
                raise ValueError(f"Thread {request.gmail_thread_id} not found")
            email_text = thread["combined_text"]
            source = "gmail"
        elif request.gmail_message_id:
            # Gmail message mode
            message = await gmail_service.get_message(request.gmail_message_id)
            if not message:
                raise ValueError(f"Message {request.gmail_message_id} not found")
            email_text = (
                f"From: {message.get('sender', '')}\n"
                f"Date: {message.get('date', '')}\n"
                f"Subject: {message.get('subject', '')}\n\n"
                f"{message.get('body', '')}"
            )
            source = "gmail"
        else:
            raise ValueError("No email source provided")
        
        # Step 2: Extract decision data using LLM
        extracted = await extract_decision_from_email(
            email_text=email_text,
            customer_name=request.customer_name,
            decision_type=request.decision_type.value
        )
        
        # Step 3: Determine decision timestamp
        decision_timestamp = self._parse_timestamp(
            extracted.get("decision_timestamp")
        ) or datetime.utcnow()
        
        request_timestamp = self._parse_timestamp(
            extracted.get("request_timestamp")
        )
        
        # Step 4: Enrich with customer data (parallel API calls)
        customer_data = await get_all_customer_data(request.customer_name)
        
        # Step 5: Get policy at decision time
        policy_data = policy_store.get_policy_at_time(decision_timestamp)
        
        # Step 6: Build decision trace components
        
        # Build request component
        decision_request = DecisionRequest(
            customer=request.customer_name,
            requested_action=extracted.get("requested_discount") or "Unknown",
            requestor_email=extracted.get("requestor_email"),
            requestor_name=extracted.get("requestor_name"),
            requested_at=request_timestamp,
            reason=extracted.get("reason")
        )
        
        # Build outcome component
        outcome_str = extracted.get("outcome", "pending").lower()
        outcome_map = {
            "approved": DecisionOutcome.APPROVED,
            "rejected": DecisionOutcome.REJECTED,
            "modified": DecisionOutcome.MODIFIED,
            "escalated": DecisionOutcome.ESCALATED,
            "pending": DecisionOutcome.PENDING,
        }
        outcome = outcome_map.get(outcome_str, DecisionOutcome.PENDING)
        
        decision_outcome = DecisionOutcomeData(
            outcome=outcome,
            final_action=extracted.get("final_discount") or extracted.get("requested_discount") or "Unknown",
            decision_maker_email=extracted.get("decision_maker_email"),
            decision_maker_name=extracted.get("decision_maker_name"),
            decided_at=decision_timestamp,
            reasoning=extracted.get("reasoning")
        )
        
        # Build evidence list
        evidence = self._build_evidence(customer_data, decision_timestamp)
        
        # Build policy info
        policy_info = None
        if policy_data:
            policy_info = PolicyInfo(
                version=policy_data["version"],
                effective_from=policy_data["effective_from"],
                effective_until=policy_data.get("effective_until"),
                rules=policy_data.get("rules", {}),
                exception_made=False  # Will be updated if exceptions found
            )
        
        # Step 7: Detect policy exceptions
        exceptions = self._detect_policy_exceptions(
            final_discount=extracted.get("final_discount"),
            policy_data=policy_data,
            decision_timestamp=decision_timestamp
        )
        
        # Update policy_info if exceptions were found
        if policy_info and exceptions:
            policy_info.exception_made = True
        
        # Step 7.5: Find precedents from Neo4j
        customer_industry = None
        customer_arr = None
        for ev in evidence:
            if ev.field == "industry":
                customer_industry = ev.value
            elif ev.field == "arr":
                customer_arr = ev.value
        
        precedents = await find_precedents(
            customer_industry=customer_industry,
            customer_arr=customer_arr,
            decision_type=request.decision_type.value,
            limit=5
        )
        
        # Step 8: Construct final decision trace
        decision_trace = DecisionTrace(
            decision_id=f"dec_{uuid.uuid4().hex[:12]}",
            timestamp=decision_timestamp,
            decision_type=request.decision_type,
            request=decision_request,
            decision=decision_outcome,
            evidence=evidence,
            policy=policy_info,
            precedents=precedents,  # Populated from Neo4j
            exceptions=exceptions,
            source=source,
            raw_email_text=email_text
        )
        
        # Store in memory (kept for backward compatibility)
        self._decisions[decision_trace.decision_id] = decision_trace
        
        logger.info(
            f"Decision trace {decision_trace.decision_id} created for {request.customer_name}"
        )
        
        return decision_trace
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """
        Parse ISO 8601 timestamp string to datetime.
        
        Handles various formats and returns None on failure.
        """
        if not timestamp_str:
            return None
        
        try:
            # Handle ISO 8601 format
            if "T" in timestamp_str:
                # Remove 'Z' suffix if present
                ts = timestamp_str.replace("Z", "+00:00")
                return datetime.fromisoformat(ts)
            else:
                # Try basic date parsing
                from dateutil import parser
                return parser.parse(timestamp_str)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None
    
    def _build_evidence(
        self,
        customer_data: Dict[str, Any],
        decision_timestamp: datetime
    ) -> List[Evidence]:
        """
        Build evidence list from customer data.
        
        Each piece of evidence captures the value at decision time.
        """
        evidence = []
        
        # CRM evidence
        if customer_data.get("crm"):
            crm = customer_data["crm"]
            evidence.append(Evidence(
                source="salesforce",
                field="arr",
                value=crm.get("arr"),
                captured_at=crm.get("retrieved_at", decision_timestamp)
            ))
            evidence.append(Evidence(
                source="salesforce",
                field="tier",
                value=crm.get("tier"),
                captured_at=crm.get("retrieved_at", decision_timestamp)
            ))
            evidence.append(Evidence(
                source="salesforce",
                field="industry",
                value=crm.get("industry"),
                captured_at=crm.get("retrieved_at", decision_timestamp)
            ))
        
        # Support evidence
        if customer_data.get("support"):
            support = customer_data["support"]
            evidence.append(Evidence(
                source="zendesk",
                field="sev1_tickets",
                value=support.get("sev1_tickets"),
                captured_at=support.get("retrieved_at", decision_timestamp)
            ))
            evidence.append(Evidence(
                source="zendesk",
                field="satisfaction_score",
                value=support.get("satisfaction_score"),
                captured_at=support.get("retrieved_at", decision_timestamp)
            ))
        
        # Finance evidence
        if customer_data.get("finance"):
            finance = customer_data["finance"]
            evidence.append(Evidence(
                source="stripe",
                field="margin_percent",
                value=finance.get("margin_percent"),
                captured_at=finance.get("retrieved_at", decision_timestamp)
            ))
            evidence.append(Evidence(
                source="stripe",
                field="ltv",
                value=finance.get("ltv"),
                captured_at=finance.get("retrieved_at", decision_timestamp)
            ))
            evidence.append(Evidence(
                source="stripe",
                field="payment_status",
                value=finance.get("payment_status"),
                captured_at=finance.get("retrieved_at", decision_timestamp)
            ))
        
        return evidence
    
    def _detect_policy_exceptions(
        self,
        final_discount: Optional[str],
        policy_data: Optional[Dict[str, Any]],
        decision_timestamp: datetime
    ) -> List[PolicyException]:
        """
        Detect if the decision violated any policy limits.
        
        Compares the final discount against policy limits and
        returns a list of exceptions.
        """
        exceptions = []
        
        if not final_discount or not policy_data:
            return exceptions
        
        # Parse discount percentage
        try:
            # Handle "15%" or "15" format
            discount_value = float(final_discount.replace("%", "").strip())
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse discount: {final_discount}")
            return exceptions
        
        # Get policy limits
        limits = policy_data.get("rules", {}).get("discount_limits", {})
        standard_limit = limits.get("standard_limit", 10)
        manager_limit = limits.get("manager_limit", 15)
        vp_limit = limits.get("vp_limit", 20)
        
        # Check standard limit
        if discount_value > standard_limit:
            if discount_value <= manager_limit:
                # Within manager authority - note but not a major exception
                exceptions.append(PolicyException(
                    exception_type="exceeds_standard_limit",
                    description=f"Discount {discount_value}% exceeds standard limit of {standard_limit}%",
                    policy_limit=f"{standard_limit}%",
                    actual_value=f"{discount_value}%",
                    deviation=f"{discount_value - standard_limit}%",
                    approved_by="Manager (within manager limit)"
                ))
            elif discount_value <= vp_limit:
                # Requires VP approval
                exceptions.append(PolicyException(
                    exception_type="requires_vp_approval",
                    description=f"Discount {discount_value}% exceeds manager limit of {manager_limit}%",
                    policy_limit=f"{manager_limit}%",
                    actual_value=f"{discount_value}%",
                    deviation=f"{discount_value - manager_limit}%",
                    approved_by="VP (within VP limit)"
                ))
            else:
                # Exceeds all standard limits
                exceptions.append(PolicyException(
                    exception_type="exceeds_all_standard_limits",
                    description=f"Discount {discount_value}% exceeds VP limit of {vp_limit}%",
                    policy_limit=f"{vp_limit}%",
                    actual_value=f"{discount_value}%",
                    deviation=f"{discount_value - vp_limit}%",
                    approved_by="Executive exception required"
                ))
        
        return exceptions
    
    async def get_decision(self, decision_id: str) -> Optional[DecisionTrace]:
        """
        Retrieve a decision by ID.
        
        Currently from in-memory store. Part 2 will use Neo4j.
        """
        return self._decisions.get(decision_id)
    
    async def list_decisions(
        self,
        customer_name: Optional[str] = None,
        limit: int = 50
    ) -> List[DecisionTrace]:
        """
        List decisions, optionally filtered by customer.
        """
        decisions = list(self._decisions.values())
        
        if customer_name:
            decisions = [
                d for d in decisions 
                if d.request.customer.lower() == customer_name.lower()
            ]
        
        # Sort by timestamp descending
        decisions.sort(key=lambda d: d.timestamp, reverse=True)
        
        return decisions[:limit]


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

decision_engine = DecisionEngine()


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

async def construct_decision_trace(request: EmailIngestionRequest) -> DecisionTrace:
    """Convenience function for decision trace construction."""
    return await decision_engine.construct_decision_trace(request)
