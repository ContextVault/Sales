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
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    EmailIngestionRequest,
    DecisionTrace,
    HealthCheckResponse,
    SearchResult,
    EmailMessage,
    PolicyVersionResponse,
    APIError,
)
from .decision_engine import decision_engine
from .gmail_service import gmail_service
from .gemini_service import gemini_service
from .policy_store import get_all_policies, get_current_policy
from .mock_apis import router as mock_api_router
from .neo4j_service import neo4j_service
from .graph_operations import (
    save_decision_trace,
    get_decision_by_id,
    get_pattern_analysis,
    list_recent_decisions
)

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
# POLICY ENDPOINTS
# =============================================================================

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
    Get formatted ground truth explanation of a decision.
    
    Returns a human-readable explanation with all context.
    """
    decision = await get_decision_by_id(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    
    # Format explanation
    explanation = {
        "decision_id": decision_id,
        "summary": f"{decision.get('outcome', 'Unknown').title()}: {decision.get('final_action', 'Unknown')} for {decision.get('customer_name', 'Unknown')}",
        "decision_maker": decision.get("decision_maker_email"),
        "timestamp": str(decision.get("timestamp")),
        "reasoning": decision.get("decision_reasoning"),
        "evidence": {
            f"{e.get('field', 'unknown')} ({e.get('source', 'unknown')})": e.get('value')
            for e in decision.get("evidence", [])
        },
        "policy": decision.get("policy"),
        "precedents_count": len(decision.get("precedents", [])),
        "full_trace": decision
    }
    
    return explanation


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
