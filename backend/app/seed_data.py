"""
Seed Data - Generate and Load Sample Decisions

Creates 15 realistic sample decisions to populate the Neo4j database
for testing and demonstration purposes.

Usage:
    python -m app.seed_data
"""
import asyncio
import random
import uuid
import sys
import os
from datetime import datetime, timedelta
from typing import List

# Load environment variables first
from dotenv import load_dotenv
load_dotenv()

from faker import Faker

# Add parent to path for module imports
sys.path.insert(0, '.')

from app.models import (
    DecisionTrace, DecisionRequest, DecisionOutcomeData,
    Evidence, PolicyInfo, PolicyException,
    DecisionType, DecisionOutcome, Precedent
)
from app.graph_operations import save_decision_trace
from app.policy_store import get_policy_at_time
from app.neo4j_service import neo4j_service

fake = Faker()

# =============================================================================
# SAMPLE DATA
# =============================================================================

# Sample customers (matching mock_apis.py data)
CUSTOMERS = [
    {"name": "MedTech Corp", "industry": "healthcare", "arr": 450000, "tier": "enterprise", "sev1": 3, "margin": 32},
    {"name": "HealthTech Inc", "industry": "healthcare", "arr": 320000, "tier": "enterprise", "sev1": 1, "margin": 38},
    {"name": "BioPharm LLC", "industry": "biotech", "arr": 180000, "tier": "growth", "sev1": 0, "margin": 42},
    {"name": "FinServe Co", "industry": "financial_services", "arr": 620000, "tier": "enterprise", "sev1": 2, "margin": 28},
    {"name": "TechStartup XYZ", "industry": "technology", "arr": 45000, "tier": "startup", "sev1": 0, "margin": 55},
    {"name": "RetailGiant Plus", "industry": "retail", "arr": 280000, "tier": "growth", "sev1": 1, "margin": 35},
    {"name": "ManufactureMax", "industry": "manufacturing", "arr": 520000, "tier": "enterprise", "sev1": 0, "margin": 30},
]

# Sample employees
SALES_REPS = [
    "john.sales@company.com",
    "sarah.sales@company.com",
    "mike.sales@company.com",
    "lisa.sales@company.com"
]

MANAGERS = [
    "jane.manager@company.com",
    "bob.manager@company.com"
]

VPS = [
    "tom.vp@company.com",
    "alice.vp@company.com"
]


# =============================================================================
# DECISION GENERATOR
# =============================================================================

def generate_decision(
    decision_num: int,
    customer: dict,
    days_ago: int
) -> DecisionTrace:
    """
    Generate a realistic decision trace.
    
    Args:
        decision_num: Decision number for unique ID generation
        customer: Customer data dict
        days_ago: How many days ago the decision was made
        
    Returns:
        Complete DecisionTrace ready to save
    """
    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    timestamp = datetime.utcnow() - timedelta(days=days_ago)
    
    # Random discount request (weighted towards realistic values)
    discount_options = [
        ("8%", 8), ("10%", 10), ("12%", 12), 
        ("15%", 15), ("18%", 18), ("20%", 20), ("25%", 25)
    ]
    weights = [15, 25, 20, 20, 10, 7, 3]  # More likely to request lower discounts
    requested_discount, requested_pct = random.choices(discount_options, weights=weights)[0]
    
    # Determine outcome based on request and customer factors
    if requested_pct <= 10:
        # Within standard limit - almost always approved
        outcome = DecisionOutcome.APPROVED
        final_discount = requested_discount
        approver = random.choice(MANAGERS)
    elif requested_pct <= 15:
        # Needs manager - usually approved, sometimes modified
        if random.random() > 0.15:
            if random.random() > 0.3:
                outcome = DecisionOutcome.APPROVED
                final_discount = requested_discount
            else:
                outcome = DecisionOutcome.MODIFIED
                final_discount = f"{requested_pct - 2}%"
        else:
            outcome = DecisionOutcome.REJECTED
            final_discount = "0%"
        approver = random.choice(MANAGERS)
    else:
        # Needs VP - mixed outcomes
        if customer["arr"] > 400000 or customer["sev1"] > 0:
            # High value customer or incidents - more likely approved
            if random.random() > 0.25:
                outcome = random.choice([DecisionOutcome.APPROVED, DecisionOutcome.MODIFIED])
                final_discount = str(min(requested_pct, 20)) + "%" if outcome == DecisionOutcome.MODIFIED else requested_discount
            else:
                outcome = DecisionOutcome.REJECTED
                final_discount = "0%"
        else:
            # Regular customer - more scrutiny
            if random.random() > 0.4:
                outcome = DecisionOutcome.MODIFIED
                final_discount = str(min(requested_pct, 15)) + "%"
            else:
                outcome = DecisionOutcome.REJECTED
                final_discount = "0%"
        approver = random.choice(VPS)
    
    requestor = random.choice(SALES_REPS)
    
    # Get policy at decision time
    policy_data = get_policy_at_time(timestamp)
    
    # Detect exceptions
    exceptions: List[PolicyException] = []
    final_pct = int(final_discount.strip('%')) if final_discount != "0%" else 0
    
    if policy_data and final_pct > 0:
        limits = policy_data.get("rules", {}).get("discount_limits", {})
        standard_limit = limits.get("standard_limit", 10)
        
        if final_pct > standard_limit and outcome in [DecisionOutcome.APPROVED, DecisionOutcome.MODIFIED]:
            exceptions.append(
                PolicyException(
                    exception_type="exceeds_standard_limit",
                    description=f"Discount {final_discount} exceeds standard limit of {standard_limit}%",
                    policy_limit=f"{standard_limit}%",
                    actual_value=final_discount,
                    deviation=f"{final_pct - standard_limit}%"
                )
            )
    
    # Generate reasoning
    reasons = []
    if customer['sev1'] > 0:
        reasons.append(f"{customer['sev1']} SEV-1 incidents")
    if customer['arr'] > 400000:
        reasons.append("high-value customer")
    if customer['margin'] < 35:
        reasons.append("lower margin")
    if not reasons:
        reasons.append("standard renewal request")
    
    request_reason = ", ".join(reasons)
    
    if outcome == DecisionOutcome.APPROVED:
        decision_reasoning = f"Approved based on: {request_reason}"
    elif outcome == DecisionOutcome.MODIFIED:
        decision_reasoning = f"Modified to {final_discount} - original request too high. Considered: {request_reason}"
    else:
        decision_reasoning = f"Rejected - request exceeds limits without sufficient justification"
    
    # Build policy info
    policy_info = None
    if policy_data:
        policy_info = PolicyInfo(
            version=policy_data["version"],
            effective_from=policy_data["effective_from"],
            effective_until=policy_data.get("effective_until"),
            rules=policy_data.get("rules", {}),
            exception_made=len(exceptions) > 0
        )
    
    # Create decision trace
    trace = DecisionTrace(
        decision_id=decision_id,
        timestamp=timestamp,
        decision_type=DecisionType.DISCOUNT_APPROVAL,
        request=DecisionRequest(
            customer=customer['name'],
            requested_action=f"{requested_discount} discount",
            requestor_email=requestor,
            requestor_name=requestor.split('@')[0].replace('.', ' ').title(),
            requested_at=timestamp - timedelta(minutes=random.randint(5, 60)),
            reason=request_reason
        ),
        decision=DecisionOutcomeData(
            outcome=outcome,
            final_action=f"{final_discount} discount" if outcome != DecisionOutcome.REJECTED else "rejected",
            decision_maker_email=approver,
            decision_maker_name=approver.split('@')[0].replace('.', ' ').title(),
            decided_at=timestamp,
            reasoning=decision_reasoning
        ),
        evidence=[
            Evidence(source="salesforce", field="arr", value=customer['arr'], captured_at=timestamp),
            Evidence(source="salesforce", field="industry", value=customer['industry'], captured_at=timestamp),
            Evidence(source="salesforce", field="tier", value=customer['tier'], captured_at=timestamp),
            Evidence(source="zendesk", field="sev1_tickets", value=customer['sev1'], captured_at=timestamp),
            Evidence(source="stripe", field="margin_percent", value=customer['margin'], captured_at=timestamp)
        ],
        policy=policy_info,
        precedents=[],  # Will be empty for seed data
        exceptions=exceptions,
        source="seed_data"
    )
    
    return trace


# =============================================================================
# MAIN SEED FUNCTION
# =============================================================================

async def seed_database():
    """Seed Neo4j with 15 sample decisions."""
    print("🌱 Seeding Neo4j database with sample decisions...")
    print(f"   Neo4j URI: {neo4j_service.uri}")
    print()
    
    # Check connection
    if not neo4j_service.is_connected():
        print("❌ Neo4j is not connected. Please check your connection settings.")
        print("   Make sure NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD are set in .env")
        return
    
    decisions = []
    
    # Generate 15 decisions spread over 90 days
    for i in range(15):
        customer = random.choice(CUSTOMERS)
        days_ago = random.randint(1, 90)
        
        decision = generate_decision(i + 1, customer, days_ago)
        decisions.append(decision)
    
    # Sort by timestamp for consistent precedent relationships
    decisions.sort(key=lambda d: d.timestamp)
    
    # Save all decisions
    success_count = 0
    for i, decision in enumerate(decisions, 1):
        print(f"  [{i:2d}/15] Saving: {decision.decision_id}")
        print(f"          Customer: {decision.request.customer}")
        print(f"          Outcome: {decision.decision.outcome.value} - {decision.decision.final_action}")
        
        success = await save_decision_trace(decision)
        if success:
            print(f"          ✅ Saved")
            success_count += 1
        else:
            print(f"          ❌ Failed")
        print()
    
    print("=" * 50)
    print(f"✅ Seeding complete!")
    print(f"   Successfully saved: {success_count}/15 decisions")
    
    # Print stats
    stats = neo4j_service.get_stats()
    print(f"\n📊 Database Statistics:")
    print(f"   Decisions: {stats['nodes']['decision']}")
    print(f"   People: {stats['nodes']['person']}")
    print(f"   Policies: {stats['nodes']['policy']}")
    print(f"   Evidence: {stats['nodes']['evidence']}")
    print(f"   Customers: {stats['nodes']['customer']}")
    print(f"   Total Relationships: {stats['relationships']}")


if __name__ == "__main__":
    asyncio.run(seed_database())
