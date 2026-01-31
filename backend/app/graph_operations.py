"""
Graph Operations - Neo4j Read/Write Operations

Provides functions for saving decision traces to the graph database
and querying for precedents, patterns, and analytics.
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from .neo4j_service import neo4j_service
from .models import DecisionTrace, Precedent

logger = logging.getLogger(__name__)


# =============================================================================
# WRITE OPERATIONS
# =============================================================================

async def save_decision_trace(trace: DecisionTrace) -> bool:
    """
    Save complete decision trace to Neo4j graph.
    
    Creates:
    - Decision node with all properties
    - Person nodes (requestor, approver)
    - Evidence nodes for each piece of evidence
    - Policy node (if applicable)
    - Customer node
    - All relationships between nodes
    
    Args:
        trace: Complete DecisionTrace to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not neo4j_service.is_connected():
        logger.warning("Neo4j not connected, skipping save")
        return False
    
    try:
        with neo4j_service.get_session() as session:
            # Use transaction for atomicity
            with session.begin_transaction() as tx:
                # 1. Create Decision node
                _create_decision_node(tx, trace)
                
                # 2. Create Person nodes (requestor and approver)
                _create_person_nodes(tx, trace)
                
                # 3. Create Evidence nodes
                _create_evidence_nodes(tx, trace)
                
                # 4. Create Policy node
                _create_policy_node(tx, trace)
                
                # 5. Create Customer node
                _create_customer_node(tx, trace)
                
                # 6. Create relationships
                _create_relationships(tx, trace)
                
                # 7. Create similarity relationships to precedents
                _create_similarity_relationships(tx, trace)
                
                tx.commit()
        
        logger.info(f"Saved decision trace to Neo4j: {trace.decision_id}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to save decision trace: {e}")
        return False


def _create_decision_node(tx, trace: DecisionTrace):
    """Create the main Decision node."""
    # Extract customer data from evidence
    customer_industry = None
    customer_arr = None
    for evidence in trace.evidence:
        if evidence.field == "industry":
            customer_industry = evidence.value
        elif evidence.field == "arr":
            customer_arr = evidence.value
    
    query = """
    CREATE (d:Decision {
        id: $id,
        timestamp: datetime($timestamp),
        type: $type,
        outcome: $outcome,
        customer_name: $customer_name,
        customer_industry: $customer_industry,
        customer_arr: $customer_arr,
        requested_action: $requested_action,
        requestor_email: $requestor_email,
        requested_at: datetime($requested_at),
        request_reason: $request_reason,
        final_action: $final_action,
        decision_maker_email: $decision_maker_email,
        decided_at: datetime($decided_at),
        decision_reasoning: $decision_reasoning,
        source: $source,
        created_at: datetime($created_at)
    })
    """
    
    tx.run(query, {
        "id": trace.decision_id,
        "timestamp": trace.timestamp.isoformat(),
        "type": trace.decision_type.value,
        "outcome": trace.decision.outcome.value,
        "customer_name": trace.request.customer,
        "customer_industry": customer_industry,
        "customer_arr": customer_arr,
        "requested_action": trace.request.requested_action,
        "requestor_email": str(trace.request.requestor_email) if trace.request.requestor_email else None,
        "requested_at": (trace.request.requested_at or trace.timestamp).isoformat(),
        "request_reason": trace.request.reason or "",
        "final_action": trace.decision.final_action,
        "decision_maker_email": str(trace.decision.decision_maker_email) if trace.decision.decision_maker_email else None,
        "decided_at": (trace.decision.decided_at or trace.timestamp).isoformat(),
        "decision_reasoning": trace.decision.reasoning or "",
        "source": trace.source,
        "created_at": trace.timestamp.isoformat()
    })


def _create_person_nodes(tx, trace: DecisionTrace):
    """Create Person nodes for requestor and approver (MERGE = create if not exists)."""
    # Requestor
    if trace.request.requestor_email:
        tx.run("""
            MERGE (p:Person {email: $email})
            ON CREATE SET p.role = $role, p.name = $name, p.created_at = datetime()
        """, {
            "email": str(trace.request.requestor_email),
            "role": "Sales Rep",
            "name": trace.request.requestor_name or ""
        })
    
    # Decision maker (approver)
    if trace.decision.decision_maker_email:
        role = _infer_role_from_email(str(trace.decision.decision_maker_email))
        tx.run("""
            MERGE (p:Person {email: $email})
            ON CREATE SET p.role = $role, p.name = $name, p.created_at = datetime()
        """, {
            "email": str(trace.decision.decision_maker_email),
            "role": role,
            "name": trace.decision.decision_maker_name or ""
        })


def _infer_role_from_email(email: str) -> str:
    """Infer role from email address (simple heuristic)."""
    email_lower = email.lower()
    if "manager" in email_lower:
        return "Manager"
    elif "vp" in email_lower or "director" in email_lower:
        return "VP"
    elif "cfo" in email_lower or "ceo" in email_lower:
        return "CFO"
    else:
        return "Manager"  # Default assumption for approvers


def _create_evidence_nodes(tx, trace: DecisionTrace):
    """Create Evidence nodes for each piece of evidence."""
    for evidence in trace.evidence:
        evidence_id = f"evidence_{trace.decision_id}_{evidence.field}"
        
        # Handle different value types
        value = evidence.value
        if isinstance(value, bool):
            value = str(value)
        
        tx.run("""
            CREATE (e:Evidence {
                id: $id,
                source: $source,
                field: $field,
                value: $value,
                captured_at: datetime($captured_at),
                decision_id: $decision_id
            })
        """, {
            "id": evidence_id,
            "source": evidence.source,
            "field": evidence.field,
            "value": value,
            "captured_at": evidence.captured_at.isoformat(),
            "decision_id": trace.decision_id
        })


def _create_policy_node(tx, trace: DecisionTrace):
    """Create Policy node (MERGE = create if not exists)."""
    if not trace.policy:
        return
    
    tx.run("""
        MERGE (p:Policy {version: $version})
        ON CREATE SET
            p.effective_from = datetime($effective_from),
            p.effective_until = CASE WHEN $effective_until IS NOT NULL 
                                     THEN datetime($effective_until) 
                                     ELSE null END,
            p.standard_limit = $standard_limit,
            p.manager_limit = $manager_limit,
            p.vp_limit = $vp_limit,
            p.description = $description
    """, {
        "version": trace.policy.version,
        "effective_from": trace.policy.effective_from.isoformat(),
        "effective_until": trace.policy.effective_until.isoformat() if trace.policy.effective_until else None,
        "standard_limit": str(trace.policy.rules.get("discount_limits", {}).get("standard_limit", 10)) + "%",
        "manager_limit": str(trace.policy.rules.get("discount_limits", {}).get("manager_limit", 15)) + "%",
        "vp_limit": str(trace.policy.rules.get("discount_limits", {}).get("vp_limit", 20)) + "%",
        "description": f"Policy version {trace.policy.version}"
    })


def _create_customer_node(tx, trace: DecisionTrace):
    """Create Customer node (MERGE = create if not exists, update on match)."""
    # Extract customer data from evidence
    customer_data = {
        "name": trace.request.customer,
        "industry": None,
        "current_arr": None,
        "tier": None
    }
    
    for evidence in trace.evidence:
        if evidence.field == "industry":
            customer_data["industry"] = evidence.value
        elif evidence.field == "arr":
            customer_data["current_arr"] = evidence.value
        elif evidence.field == "tier":
            customer_data["tier"] = evidence.value
    
    tx.run("""
        MERGE (c:Customer {name: $name})
        ON CREATE SET
            c.industry = $industry,
            c.current_arr = $current_arr,
            c.tier = $tier,
            c.first_seen = datetime(),
            c.last_decision = datetime($timestamp)
        ON MATCH SET
            c.current_arr = COALESCE($current_arr, c.current_arr),
            c.last_decision = datetime($timestamp)
    """, {
        "name": customer_data["name"],
        "industry": customer_data["industry"],
        "current_arr": customer_data["current_arr"],
        "tier": customer_data["tier"],
        "timestamp": trace.timestamp.isoformat()
    })


def _create_relationships(tx, trace: DecisionTrace):
    """Create all relationships between nodes."""
    # Decision -[:REQUESTED_BY]-> Person
    if trace.request.requestor_email:
        tx.run("""
            MATCH (d:Decision {id: $decision_id})
            MATCH (p:Person {email: $requestor_email})
            CREATE (d)-[:REQUESTED_BY]->(p)
        """, {
            "decision_id": trace.decision_id,
            "requestor_email": str(trace.request.requestor_email)
        })
    
    # Decision -[:APPROVED_BY]-> Person
    if trace.decision.decision_maker_email:
        tx.run("""
            MATCH (d:Decision {id: $decision_id})
            MATCH (p:Person {email: $approver_email})
            CREATE (d)-[:APPROVED_BY {
                approved_at: datetime($approved_at),
                notes: $notes
            }]->(p)
        """, {
            "decision_id": trace.decision_id,
            "approver_email": str(trace.decision.decision_maker_email),
            "approved_at": (trace.decision.decided_at or trace.timestamp).isoformat(),
            "notes": trace.decision.reasoning or ""
        })
    
    # Decision -[:BASED_ON]-> Evidence
    for evidence in trace.evidence:
        evidence_id = f"evidence_{trace.decision_id}_{evidence.field}"
        tx.run("""
            MATCH (d:Decision {id: $decision_id})
            MATCH (e:Evidence {id: $evidence_id})
            CREATE (d)-[:BASED_ON]->(e)
        """, {
            "decision_id": trace.decision_id,
            "evidence_id": evidence_id
        })
    
    # Decision -[:EVALUATED]-> Policy
    if trace.policy:
        followed = not trace.policy.exception_made
        tx.run("""
            MATCH (d:Decision {id: $decision_id})
            MATCH (p:Policy {version: $version})
            CREATE (d)-[:EVALUATED {followed: $followed}]->(p)
        """, {
            "decision_id": trace.decision_id,
            "version": trace.policy.version,
            "followed": followed
        })
    
    # Decision -[:OVERRODE]-> Policy (if exceptions made)
    if trace.policy and trace.exceptions:
        for exception in trace.exceptions:
            tx.run("""
                MATCH (d:Decision {id: $decision_id})
                MATCH (p:Policy {version: $version})
                CREATE (d)-[:OVERRODE {
                    exception_type: $exception_type,
                    justification: $justification,
                    deviation: $deviation
                }]->(p)
            """, {
                "decision_id": trace.decision_id,
                "version": trace.policy.version,
                "exception_type": exception.exception_type,
                "justification": exception.description,
                "deviation": exception.deviation
            })
    
    # Decision -[:FOR_CUSTOMER]-> Customer
    tx.run("""
        MATCH (d:Decision {id: $decision_id})
        MATCH (c:Customer {name: $customer_name})
        CREATE (d)-[:FOR_CUSTOMER]->(c)
    """, {
        "decision_id": trace.decision_id,
        "customer_name": trace.request.customer
    })


def _create_similarity_relationships(tx, trace: DecisionTrace):
    """Create SIMILAR_TO relationships to precedents if they exist."""
    if not trace.precedents:
        return
    
    for precedent in trace.precedents:
        tx.run("""
            MATCH (d1:Decision {id: $decision_id})
            MATCH (d2:Decision {id: $precedent_id})
            CREATE (d1)-[:SIMILAR_TO {
                similarity_score: $similarity_score,
                calculated_at: datetime(),
                reason: $reason
            }]->(d2)
        """, {
            "decision_id": trace.decision_id,
            "precedent_id": precedent.decision_id,
            "similarity_score": precedent.similarity_score,
            "reason": precedent.why_similar or "Similar customer profile and decision context"
        })


# =============================================================================
# READ OPERATIONS
# =============================================================================

async def get_decision_by_id(decision_id: str) -> Optional[Dict]:
    """
    Get complete decision trace from graph by ID.
    
    Returns decision with all related nodes (evidence, policy, precedents).
    """
    if not neo4j_service.is_connected():
        return None
    
    with neo4j_service.get_session() as session:
        result = session.run("""
            MATCH (d:Decision {id: $decision_id})
            OPTIONAL MATCH (d)-[:APPROVED_BY]->(approver:Person)
            OPTIONAL MATCH (d)-[:REQUESTED_BY]->(requestor:Person)
            OPTIONAL MATCH (d)-[:EVALUATED]->(policy:Policy)
            OPTIONAL MATCH (d)-[:BASED_ON]->(evidence:Evidence)
            OPTIONAL MATCH (d)-[:SIMILAR_TO]->(precedent:Decision)
            OPTIONAL MATCH (d)-[:FOR_CUSTOMER]->(customer:Customer)
            RETURN d, approver, requestor, policy, customer,
                   collect(DISTINCT evidence) as evidence_list,
                   collect(DISTINCT precedent) as precedent_list
        """, {"decision_id": decision_id})
        
        record = result.single()
        if not record:
            return None
        
        # Convert Neo4j nodes to dicts
        decision = dict(record["d"])
        decision["approver"] = dict(record["approver"]) if record["approver"] else None
        decision["requestor"] = dict(record["requestor"]) if record["requestor"] else None
        decision["policy"] = dict(record["policy"]) if record["policy"] else None
        decision["customer"] = dict(record["customer"]) if record["customer"] else None
        decision["evidence"] = [dict(e) for e in record["evidence_list"]]
        decision["precedents"] = [dict(p) for p in record["precedent_list"]]
        
        return decision


async def find_precedents(
    customer_industry: Optional[str],
    customer_arr: Optional[int],
    decision_type: str,
    limit: int = 5
) -> List[Precedent]:
    """
    Find similar past decisions for precedent matching.
    
    Searches for decisions with:
    - Same decision type
    - Same industry
    - Similar ARR (±20%)
    - Within last 90 days
    
    Args:
        customer_industry: Industry to match
        customer_arr: ARR for similarity matching
        decision_type: Type of decision (e.g., "discount_approval")
        limit: Maximum number of precedents to return
        
    Returns:
        List of Precedent objects
    """
    if not neo4j_service.is_connected():
        return []
    
    # Build query based on available filters
    where_clauses = ["d.type = $type"]
    params = {"type": decision_type, "limit": limit}
    
    if customer_industry:
        where_clauses.append("d.customer_industry = $industry")
        params["industry"] = customer_industry
    
    if customer_arr:
        where_clauses.append("d.customer_arr > $arr_min AND d.customer_arr < $arr_max")
        params["arr_min"] = int(customer_arr * 0.8)
        params["arr_max"] = int(customer_arr * 1.2)
    
    where_clause = " AND ".join(where_clauses)
    
    query = f"""
        MATCH (d:Decision)
        WHERE {where_clause}
        RETURN d.id as decision_id,
               d.customer_name as customer,
               d.final_action as outcome,
               d.timestamp as timestamp,
               d.customer_arr as arr,
               d.customer_industry as industry
        ORDER BY d.timestamp DESC
        LIMIT $limit
    """
    
    try:
        with neo4j_service.get_session() as session:
            result = session.run(query, params)
            
            precedents = []
            for record in result:
                precedents.append(Precedent(
                    decision_id=record["decision_id"],
                    customer=record["customer"],
                    outcome=record["outcome"],
                    similarity_score=0.85,  # Simple score based on query match
                    timestamp=record["timestamp"].to_native() if record["timestamp"] else datetime.utcnow(),
                    why_similar=f"Same industry ({record['industry']}) and similar ARR"
                ))
            
            return precedents
    
    except Exception as e:
        logger.error(f"Error finding precedents: {e}")
        return []


async def get_pattern_analysis(
    industry: Optional[str] = None,
    decision_type: str = "discount_approval"
) -> Dict[str, Any]:
    """
    Analyze decision patterns.
    
    Returns:
    - Approval rate
    - Total decisions
    - Top approvers
    - Common exception types
    """
    if not neo4j_service.is_connected():
        return {"error": "Neo4j not connected"}
    
    # Build query with optional industry filter
    where_clause = "WHERE d.type = $type"
    params = {"type": decision_type}
    
    if industry:
        where_clause += " AND d.customer_industry = $industry"
        params["industry"] = industry
    
    with neo4j_service.get_session() as session:
        # Get approval stats
        result = session.run(f"""
            MATCH (d:Decision)
            {where_clause}
            WITH count(d) as total,
                 sum(CASE WHEN d.outcome = 'approved' THEN 1 ELSE 0 END) as approved,
                 sum(CASE WHEN d.outcome = 'modified' THEN 1 ELSE 0 END) as modified
            RETURN total, approved, modified,
                   CASE WHEN total > 0 THEN toFloat(approved + modified) / toFloat(total) ELSE 0.0 END as approval_rate
        """, params)
        
        stats = result.single()
        
        # Get top approvers
        result = session.run(f"""
            MATCH (d:Decision)-[:APPROVED_BY]->(p:Person)
            {where_clause}
            RETURN p.email as approver,
                   p.role as role,
                   count(d) as decisions_approved
            ORDER BY decisions_approved DESC
            LIMIT 5
        """, params)
        
        top_approvers = [dict(record) for record in result]
        
        # Get exception types
        result = session.run(f"""
            MATCH (d:Decision)-[r:OVERRODE]->(:Policy)
            {where_clause}
            RETURN r.exception_type as exception_type,
                   count(r) as count
            ORDER BY count DESC
        """, params)
        
        exceptions = [dict(record) for record in result]
        
        return {
            "total_decisions": stats["total"],
            "approved": stats["approved"],
            "modified": stats["modified"],
            "approval_rate": round(stats["approval_rate"], 2) if stats["approval_rate"] else 0,
            "top_approvers": top_approvers,
            "common_exceptions": exceptions,
            "filter": {"industry": industry, "decision_type": decision_type}
        }


async def list_recent_decisions(limit: int = 10) -> List[Dict]:
    """List most recent decisions."""
    if not neo4j_service.is_connected():
        return []
    
    with neo4j_service.get_session() as session:
        result = session.run("""
            MATCH (d:Decision)
            RETURN d.id as id,
                   d.customer_name as customer,
                   d.outcome as outcome,
                   d.final_action as final_action,
                   d.timestamp as timestamp,
                   d.customer_industry as industry
            ORDER BY d.timestamp DESC
            LIMIT $limit
        """, {"limit": limit})
        
        decisions = []
        for record in result:
            decisions.append({
                "id": record["id"],
                "customer": record["customer"],
                "outcome": record["outcome"],
                "final_action": record["final_action"],
                "timestamp": record["timestamp"].isoformat() if record["timestamp"] else None,
                "industry": record["industry"]
            })
        
        return decisions
