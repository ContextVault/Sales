"""
FastAPI Application Entry Point

Context Graph Decision Engine API - captures organizational decision traces
at execution time and stores them for ground truth retrieval.

Endpoints:
- GET /           - Welcome message
- GET /health     - Health check (Gmail, Gemini, mock APIs)
- POST /decision/ingest - Main decision trace ingestion
- GET /decision/{id}    - Get decision by ID
- GET /gmail/search     - Search Gmail
- GET /gmail/message/{id} - Get specific email
- GET /policies         - List all policy versions
- GET /api/mock/*       - Mock API endpoints (CRM, Support, Finance)
"""
import logging
import os
import uuid
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    EmailIngestionRequest,
    DecisionTrace,
    HealthCheckResponse,
    SearchResult,
    EmailMessage,
    PolicyVersionResponse,
    APIError,
    DiscountRequest,
    EnrichedRequest,
)
from .decision_engine import decision_engine
from .gmail_service import gmail_service
from .gemini_service import gemini_service
from .policy_store import get_all_policies, get_current_policy
from .mock_apis import router as mock_api_router, get_all_customer_data
from .neo4j_service import neo4j_service
from .graph_operations import (
    save_decision_trace,
    get_decision_by_id,
    get_pattern_analysis,
    list_recent_decisions,
    find_semantic_precedents
)
from .gmail_monitor import gmail_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =============================================================================
# APPLICATION SETUP
# =============================================================================

app = FastAPI(
    title="Context Graph Decision Engine",
    description="""
    A passive observation system that captures organizational decision traces 
    at execution time and stores them as an immutable graph database for 
    ground truth retrieval.
    
    ## Features
    - **Decision Trace Capture**: Capture decisions from email threads
    - **Context Enrichment**: Enrich with CRM, Support, Finance data
    - **Policy Tracking**: Track which policy version was active
    - **Exception Detection**: Detect policy violations
    
    ## Usage Modes
    1. **Gmail Mode**: Provide `gmail_message_id` to fetch from Gmail API
    2. **Manual Mode**: Paste email text directly via `email_thread` field
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include mock API router
app.include_router(mock_api_router)


# =============================================================================
# HEALTH & INFO ENDPOINTS
# =============================================================================

@app.get("/", tags=["Info"])
async def root():
    """
    Welcome message and API overview.
    """
    return {
        "name": "Context Graph Decision Engine",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "ingest": "/decision/ingest",
            "gmail_search": "/gmail/search",
            "policies": "/policies",
            "mock_apis": "/api/mock/customers"
        }
    }


@app.get("/health", response_model=HealthCheckResponse, tags=["Info"])
async def health_check():
    """
    Detailed health check for all services.
    
    Checks:
    - Gmail API connection (requires OAuth setup)
    - Gemini API availability
    - Mock APIs status
    """
    # Check Gmail connection
    gmail_status = gmail_service.check_connection()
    gmail_msg = gmail_status.get("message", "unknown")
    if gmail_status.get("connected"):
        gmail_result = "connected"
    elif not gmail_status.get("credentials_exist"):
        gmail_result = "credentials_missing"
    elif not gmail_status.get("token_exists"):
        gmail_result = "oauth_required"
    else:
        gmail_result = "error"
    
    # Check Gemini status
    gemini_status = gemini_service.check_status()
    if gemini_status.get("available"):
        gemini_result = "available"
    else:
        gemini_result = "not_configured"
    
    # Check Neo4j status
    neo4j_result = "connected" if neo4j_service.health_check() else "disconnected"
    
    return HealthCheckResponse(
        status="healthy",
        gmail=gmail_result,
        gemini=gemini_result,
        neo4j=neo4j_result,
        mock_apis="available",
        timestamp=datetime.utcnow()
    )


# =============================================================================
# DECISION ENDPOINTS
# =============================================================================

@app.post(
    "/decision/ingest",
    response_model=DecisionTrace,
    tags=["Decisions"],
    responses={
        400: {"model": APIError, "description": "Invalid request"},
        500: {"model": APIError, "description": "Processing error"}
    }
)
async def ingest_decision(request: EmailIngestionRequest):
    """
    Ingest a decision from an email thread.
    
    Supports two modes:
    
    **Gmail Mode**: Provide `gmail_message_id` or `gmail_thread_id` to fetch
    directly from Gmail API. Requires OAuth authentication.
    
    **Manual Mode**: Paste the email thread text directly in `email_thread`.
    Useful for testing or when Gmail API is not available.
    
    The system will:
    1. Extract decision details using Gemini LLM
    2. Enrich with customer data from CRM/Support/Finance
    3. Determine applicable policy version
    4. Detect any policy exceptions
    5. Construct and return the complete decision trace
    
    Example request (manual mode):
    ```json
    {
        "email_thread": "From: john@company.com\\nTo: jane@company.com\\n...",
        "customer_name": "MedTech Corp"
    }
    ```
    """
    try:
        logger.info(f"Ingesting decision for customer: {request.customer_name}")
        
        decision_trace = await decision_engine.construct_decision_trace(request)
        
        # Save to Neo4j
        saved = await save_decision_trace(decision_trace)
        if not saved:
            logger.warning(f"Failed to save decision {decision_trace.decision_id} to Neo4j")
        else:
            logger.info(f"Decision trace saved to Neo4j: {decision_trace.decision_id}")
        
        return decision_trace
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get(
    "/decision/{decision_id}",
    response_model=DecisionTrace,
    tags=["Decisions"],
    responses={404: {"model": APIError}}
)
async def get_decision(decision_id: str):
    """
    Retrieve a decision trace by ID.
    
    Returns the complete decision trace including all evidence,
    policy context, and detected exceptions.
    """
    decision = await decision_engine.get_decision(decision_id)
    
    if not decision:
        raise HTTPException(
            status_code=404,
            detail=f"Decision {decision_id} not found"
        )
    
    return decision


@app.get(
    "/decisions",
    response_model=List[DecisionTrace],
    tags=["Decisions"]
)
async def list_decisions(
    customer_name: Optional[str] = Query(None, description="Filter by customer"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results")
):
    """
    List decision traces with optional filtering.
    """
    return await decision_engine.list_decisions(
        customer_name=customer_name,
        limit=limit
    )


# =============================================================================
# GMAIL ENDPOINTS
# =============================================================================

@app.get(
    "/gmail/search",
    response_model=List[SearchResult],
    tags=["Gmail"],
    responses={500: {"model": APIError}}
)
async def search_gmail(
    query: str = Query(..., description="Gmail search query"),
    max_results: int = Query(10, ge=1, le=50, description="Maximum results")
):
    """
    Search Gmail with a query string.
    
    Uses Gmail's search syntax. Examples:
    - `subject:discount approval`
    - `from:sales@company.com`
    - `after:2026/01/01 subject:pricing`
    
    **Requires Gmail OAuth authentication.**
    First-time use will open a browser for OAuth.
    """
    try:
        results = await gmail_service.search_messages(query, max_results)
        
        return [
            SearchResult(
                id=msg["id"],
                thread_id=msg["thread_id"],
                subject=msg.get("subject"),
                sender=msg.get("sender"),
                date=msg.get("date"),
                snippet=msg.get("snippet")
            )
            for msg in results
        ]
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Gmail search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Gmail search failed: {str(e)}")


@app.get(
    "/gmail/message/{message_id}",
    response_model=EmailMessage,
    tags=["Gmail"],
    responses={404: {"model": APIError}}
)
async def get_gmail_message(message_id: str):
    """
    Fetch a specific email message by ID.
    
    Returns the complete parsed message including headers and body.
    **Requires Gmail OAuth authentication.**
    """
    try:
        message = await gmail_service.get_message(message_id)
        
        if not message:
            raise HTTPException(
                status_code=404,
                detail=f"Message {message_id} not found"
            )
        
        return EmailMessage(
            id=message["id"],
            thread_id=message["thread_id"],
            subject=message.get("subject"),
            sender=message.get("sender"),
            recipients=message.get("recipients", []),
            date=message.get("date"),
            body=message.get("body"),
            labels=message.get("labels", [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/gmail/thread/{thread_id}",
    tags=["Gmail"],
    responses={404: {"model": APIError}}
)
async def get_gmail_thread(thread_id: str):
    """
    Fetch an entire email thread (conversation) by ID.
    
    Returns all messages in the conversation with combined text
    suitable for decision extraction.
    **Requires Gmail OAuth authentication.**
    """
    try:
        thread = await gmail_service.get_thread(thread_id)
        
        if not thread:
            raise HTTPException(
                status_code=404,
                detail=f"Thread {thread_id} not found"
            )
        
        return thread
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GMAIL MONITOR ENDPOINTS
# =============================================================================

@app.get(
    "/gmail/preview",
    tags=["Gmail Monitor"],
    responses={500: {"model": APIError}}
)
async def preview_gmail_inbox(
    query: str = Query("subject:discount", description="Gmail search query"),
    max_results: int = Query(5, ge=1, le=20, description="Maximum results")
):
    """
    Preview emails in Gmail matching the query.
    
    Use this to see what's available before ingesting.
    Returns emails with their IDs, subjects, senders, and dates.
    
    **Examples:**
    - `subject:discount` - Find emails with "discount" in subject
    - `subject:(discount OR approval)` - Multiple keywords
    - `subject:discount after:2026/01/30` - Recent emails only
    """
    try:
        messages = await gmail_monitor.search_decision_emails(query, max_results)
        
        return {
            "query": query,
            "count": len(messages),
            "messages": messages
        }
        
    except Exception as e:
        logger.error(f"Gmail preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/gmail/unprocessed",
    tags=["Gmail Monitor"],
    responses={500: {"model": APIError}}
)
async def get_unprocessed_emails(
    query: str = Query(
        "subject:(discount OR approval)",
        description="Gmail search query"
    ),
    max_results: int = Query(10, ge=1, le=50, description="Maximum to search")
):
    """
    List decision emails in Gmail that haven't been ingested yet.
    
    Filters out emails that have already been processed by this session.
    """
    try:
        unprocessed = await gmail_monitor.get_unprocessed_emails(query, max_results)
        stats = gmail_monitor.get_stats()
        
        return {
            "unprocessed_count": len(unprocessed),
            "processed_count": stats["processed_count"],
            "emails": unprocessed
        }
        
    except Exception as e:
        logger.error(f"Failed to get unprocessed emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/gmail/ingest/{message_id}",
    tags=["Gmail Monitor"],
    responses={
        404: {"model": APIError},
        500: {"model": APIError}
    }
)
async def ingest_gmail_message(
    message_id: str,
    customer_name: str = Query(..., description="Customer name for decision")
):
    """
    Ingest a specific Gmail message by ID.
    
    **Process:**
    1. Fetch email thread from Gmail
    2. Extract decision data with Gemini LLM
    3. Enrich with mock API data (CRM/Support/Finance)
    4. Store in Neo4j
    5. Return complete decision trace
    
    **Tip:** Use `/gmail/preview` first to get message IDs.
    """
    result = await gmail_monitor.ingest_email(
        message_id=message_id,
        customer_name=customer_name,
        auto_save=True
    )
    
    if not result["success"]:
        if "not found" in result.get("error", "").lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=500, detail=result["error"])
    
    return {
        "success": True,
        "message_id": message_id,
        "decision_id": result["decision_id"],
        "saved_to_neo4j": result["saved_to_neo4j"],
        "decision_trace": result["trace"]
    }


@app.post(
    "/gmail/batch-ingest",
    tags=["Gmail Monitor"],
    responses={500: {"model": APIError}}
)
async def batch_ingest_emails(
    query: str = Query(
        "subject:(discount OR approval)",
        description="Gmail search query"
    ),
    customer_name: Optional[str] = Query(
        None,
        description="Customer name (if not provided, extracted from subject)"
    ),
    max_results: int = Query(10, ge=1, le=50, description="Maximum to process")
):
    """
    Search Gmail and ingest all matching unprocessed emails.
    
    If `customer_name` is not provided, the system attempts to extract it
    from the email subject line. Common patterns:
    - "Discount Request - MedTech Corp" → MedTech Corp
    - "Approval Request: HealthTech Inc" → HealthTech Inc
    
    **Example:**
    ```
    POST /gmail/batch-ingest?query=subject:discount%20after:2026/01/30
    ```
    """
    try:
        result = await gmail_monitor.batch_ingest(
            query=query,
            customer_name=customer_name,
            max_results=max_results
        )
        
        return {
            "summary": {
                "total_found": result["total"],
                "successful": result["successful"],
                "failed": result["failed"]
            },
            "results": result["results"]
        }
        
    except Exception as e:
        logger.error(f"Batch ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/gmail/stats",
    tags=["Gmail Monitor"]
)
async def get_gmail_stats(
    query: str = Query(
        "subject:(discount OR approval)",
        description="Query to check for total available"
    )
):
    """
    Get statistics about Gmail monitoring.
    
    Returns:
    - Total emails matching pattern
    - Processed count (ingested this session)
    - Unprocessed count (available to ingest)
    - Last check time
    """
    # Get current stats
    stats = gmail_monitor.get_stats()
    
    # Search for total matching emails
    all_emails = await gmail_monitor.search_decision_emails(query, max_results=50)
    unprocessed = await gmail_monitor.get_unprocessed_emails(query, max_results=50)
    
    return {
        "total_matching": len(all_emails),
        "processed_count": stats["processed_count"],
        "unprocessed_count": len(unprocessed),
        "last_check_time": stats["last_check_time"],
        "query_used": query
    }



@app.get(
    "/policies",
    response_model=List[PolicyVersionResponse],
    tags=["Policies"]
)
async def list_policies():
    """
    List all policy versions.
    
    Returns policy versions in chronological order with their
    effective dates and rules. The current policy is marked.
    """
    policies = get_all_policies()
    
    return [
        PolicyVersionResponse(
            version=p["version"],
            effective_from=p["effective_from"],
            effective_until=p.get("effective_until"),
            is_current=p.get("is_current", False),
            rules=p.get("rules", {})
        )
        for p in policies
    ]


@app.get(
    "/policies/current",
    response_model=PolicyVersionResponse,
    tags=["Policies"]
)
async def get_current_policy_endpoint():
    """
    Get the currently active policy.
    """
    policy = get_current_policy()
    
    return PolicyVersionResponse(
        version=policy["version"],
        effective_from=policy["effective_from"],
        effective_until=policy.get("effective_until"),
        is_current=True,
        rules=policy.get("rules", {})
    )


# =============================================================================
# NEO4J ENDPOINTS
# =============================================================================

@app.get("/decisions/patterns", tags=["Neo4j Analytics"])
async def get_patterns(
    industry: Optional[str] = Query(None, description="Filter by industry"),
    decision_type: str = Query("discount_approval", description="Decision type")
):
    """
    Analyze decision patterns.
    
    Returns:
    - Approval rate
    - Total decisions
    - Top approvers
    - Common exception types
    """
    patterns = await get_pattern_analysis(industry, decision_type)
    return patterns


@app.get("/decision/explain/{decision_id}", tags=["Neo4j Analytics"])
async def explain_decision(decision_id: str):
    """
    Get natural language explanation of a decision (GROUND TRUTH).
    
    Now generates human-readable explanation using LLM,
    based entirely on factual data from graph (not hallucinated).
    
    Returns:
    - explanation: LLM-generated natural language explanation
    - raw_data: The underlying decision data for verification
    """
    from .explanation_service import generate_decision_explanation
    
    decision = await get_decision_by_id(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    
    # Generate natural language explanation
    explanation_text = await generate_decision_explanation(decision)
    
    # Also provide structured summary for quick reference
    structured_summary = {
        "decision_id": decision_id,
        "summary": f"{decision.get('outcome', 'Unknown').title()}: {decision.get('final_action', 'Unknown')} for {decision.get('customer_name', 'Unknown')}",
        "decision_maker": decision.get("decision_maker_email"),
        "timestamp": str(decision.get("timestamp")),
        "precedents_count": len(decision.get("precedents", []))
    }
    
    return {
        "decision_id": decision_id,
        "explanation": explanation_text,
        "structured_summary": structured_summary,
        "raw_data": decision  # Include raw data for verification
    }



@app.get("/neo4j/stats", tags=["Neo4j Analytics"])
async def get_neo4j_stats():
    """
    Get Neo4j database statistics.
    
    Returns counts of nodes and relationships.
    """
    return neo4j_service.get_stats()


@app.get("/neo4j/decisions", tags=["Neo4j Analytics"])
async def get_neo4j_decisions(limit: int = Query(10, ge=1, le=100)):
    """
    List recent decisions from Neo4j.
    
    Returns decisions ordered by timestamp descending.
    """
    decisions = await list_recent_decisions(limit)
    return {"count": len(decisions), "decisions": decisions}


# =============================================================================
# TEST/DEBUG ENDPOINTS
# =============================================================================

from pydantic import BaseModel

class ExtractTestRequest(BaseModel):
    """Request model for testing LLM extraction."""
    email_text: str
    customer_name: str


@app.post("/test/extract", tags=["Testing"])
async def test_extraction(request: ExtractTestRequest):
    """
    Test endpoint to see LLM extraction results.
    
    Useful for debugging and testing different email formats.
    Returns extracted data with confidence scores.
    
    Example:
    ```json
    {
        "email_text": "From: john@company.com\\nTo: jane@company.com\\n\\nCan we do 18%?\\n\\n---\\nFrom: jane@company.com\\n\\nLGTM",
        "customer_name": "Test Corp"
    }
    ```
    """
    extracted = await gemini_service.extract_decision_from_email(
        request.email_text,
        request.customer_name
    )
    
    return {
        "extracted_data": extracted,
        "confidence_scores": extracted.get('confidence', {}),
        "status": "success"
    }



# =============================================================================
# STARTUP/SHUTDOWN EVENTS
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    logger.info("Context Graph Decision Engine starting up...")
    logger.info("Available endpoints: /docs for API documentation")
    
    # Check Gmail credentials
    gmail_status = gmail_service.check_connection()
    if not gmail_status.get("credentials_exist"):
        logger.warning(
            "Gmail credentials.json not found. "
            "Gmail features will not work until OAuth is configured."
        )
    
    # Check Gemini API
    gemini_status = gemini_service.check_status()
    if not gemini_status.get("available"):
        logger.warning(
            "GEMINI_API_KEY not configured. "
            "LLM extraction will use fallback pattern matching."
        )
    
    # Check Neo4j connection
    if neo4j_service.is_connected():
        stats = neo4j_service.get_stats()
        logger.info(f"Neo4j connected: {stats['total_nodes']} nodes, {stats['relationships']} relationships")
    else:
        logger.warning(
            "Neo4j not connected. "
            "Graph storage features will be disabled."
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    logger.info("Context Graph Decision Engine shutting down...")
    neo4j_service.close()


# =============================================================================
# EMPLOYEE PORTAL ENDPOINTS
# =============================================================================

@app.post("/request/submit", response_model=EnrichedRequest, tags=["Employee Portal"])
async def submit_request(request: DiscountRequest):
    """
    Employee submits discount request.
    
    Returns enriched data immediately:
    1. Customer data (CRM, support, finance)
    2. Policy evaluation (limits, exceptions)
    3. Similar precedents
    4. Required approval level
    """
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    
    # 1. Gather context from mock APIs
    context = await get_all_customer_data(request.customer_name)
    
    if not context["customer_found"]:
        # Mock data if not found for smoother demo
        context["crm"] = {"arr": 0, "industry": "Unknown", "tier": "Unknown"}
        context["support"] = {"sev1_tickets": 0, "sev2_tickets": 0}
        context["finance"] = {"margin_percent": 0.0, "payment_history": "Unknown"}
    
    # 2. Get policy and evaluate
    policy = get_current_policy()
    
    # Simple parsing of requested discount (assuming "18%" or "18")
    try:
        requested_pct = float(str(request.requested_discount).replace('%', '').strip())
    except ValueError:
        requested_pct = 0.0
        
    # Get limits from policy
    limits = policy.get('rules', {}).get('discount_limits', {})
    standard_limit = float(str(limits.get('standard_limit', '10%')).replace('%', ''))
    manager_limit = float(str(limits.get('manager_limit', '15%')).replace('%', ''))
    
    requires_approval = requested_pct > standard_limit
    
    approval_level = "auto_approved"
    if requires_approval:
        if requested_pct <= manager_limit:
            approval_level = "manager"
        else:
            approval_level = "vp"
    
    # 3. Find precedents
    precedents = await find_semantic_precedents(
        decision_summary=f"{request.reason} for {request.customer_name}",
        customer_industry=context['crm'].get('industry'),
        customer_arr=context['crm'].get('arr'),
        decision_type="discount_approval"
    )
    
    # Construct response
    enriched = EnrichedRequest(
        request_id=request_id,
        customer_name=request.customer_name,
        requested_discount=request.requested_discount,
        reason=request.reason,
        requestor_email=request.requestor_email,
        enrichment={
            "crm": context['crm'] or {},
            "support": context['support'] or {},
            "finance": context['finance'] or {}
        },
        policy_evaluation={
            "version": policy['version'],
            "standard_limit": f"{standard_limit}%",
            "exceeds_limit": requires_approval,
            "deviation": f"{requested_pct - standard_limit}%" if requires_approval else "0%"
        },
        precedents=[
            {
                "customer": p.customer,
                "outcome": p.outcome,
                "similarity": p.similarity_score
            }
            for p in precedents[:5]
        ],
        requires_approval=requires_approval,
        approval_level=approval_level
    )
    
    # Store request temporarily (mock storage)
    # in a real app, save to DB
    
    return enriched


@app.post("/request/{request_id}/send-email", tags=["Employee Portal"])
async def send_approval_email(request_id: str, manager_email: str):
    """
    Generate and send approval request email to manager.
    Mocks the email sending process.
    """
    # For demo, return formatted email text
    email_body = (
        f"Hi Manager,\n\n"
        f"Discount approval request (ID: {request_id})\n\n"
        f"Please reply with approval or rejection."
    )
    
    return {
        "request_id": request_id,
        "email_subject": f"Discount Approval Request",
        "email_body": email_body,
        "to": manager_email,
        "status": "sent"
    }


@app.get("/request/{request_id}/status", tags=["Employee Portal"])
async def check_request_status(request_id: str):
    """
    Check if request has been approved.
    Mocks the approval process (auto-approves after delay).
    """
    # Simulate approval
    return {
        "request_id": request_id,
        "status": "approved",
        "approver_email": "jane.manager@company.com",
        "final_discount": "15%",
        "reasoning": "Approved based on similar precedents.",
        "approved_at": datetime.utcnow().isoformat()
    }


@app.post("/chat", tags=["Employee Portal"])
async def chat_with_knowledge_graph(request: dict = Body(...)) -> dict:
    """
    LLM chatbot that queries knowledge graph.
    """
    question = request.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="Missing question")
        
    # 1. Generate Cypher query
    query_prompt = (
        f"You are a Neo4j Cypher query expert.\n"
        f"User question: \"{question}\"\n"
        f"Generate a Cypher query to answer this question.\n"
        f"Available node types: Decision, Person, Policy, Customer\n"
        f"Available relationships: REQUESTED_BY, APPROVED_BY, EVALUATED, FOR_CUSTOMER\n\n"
        f"Return ONLY the Cypher query."
    )
    
    cypher_query = await gemini_service.chat(query_prompt)
    
    # Clean up query
    if cypher_query.startswith('```'):
        cypher_query = cypher_query.split('```')[1].replace('cypher', '').strip()
        
    # 2. Execute query
    records = []
    if neo4j_service.is_connected():
        try:
            with neo4j_service.get_session() as session:
                result = session.run(cypher_query)
                records = [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Cypher execution failed: {e}")
            pass
            
    # 3. Format answer
    # 3. Format answer
    answer_prompt = (
        f"User asked: \"{question}\"\n"
        f"Query results: {json.dumps(records, default=str)}\n\n"
        f"Format this into a clear, natural language answer."
    )
    
    answer = await gemini_service.chat(answer_prompt)
    
    return {
        "question": question,
        "answer": answer,
        "data": records,
        "cypher_query": cypher_query
    }

