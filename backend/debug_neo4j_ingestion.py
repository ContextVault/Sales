
import asyncio
import logging
import sys
import os

# Add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ingestion():
    print("Simulating app startup by importing app.main...")
    # This should trigger load_dotenv()
    import app.main
    
    # Now import the service which should have been initialized with env vars
    from app.neo4j_service import neo4j_service
    from app.decision_engine import decision_engine
    from app.models import EmailIngestionRequest, DecisionType
    from app.graph_operations import save_decision_trace

    print("Checking Neo4j connection...")
    if not neo4j_service.is_connected():
        print("Neo4j is NOT connected. Attempting manual connect (though init should have done it)...")
        # Initialize connection if not already
        neo4j_service._connect()
        
    if neo4j_service.is_connected():
        print("SUCCESS: Neo4j is connected.")
    else:
        print("FAILURE: Neo4j is still NOT connected.")
        return

    # Create a dummy decision trace
    print("Creating dummy decision trace...")
    request = EmailIngestionRequest(
        email_thread="From: verification@example.com\nTo: sales@company.com\n\nI approve the 10% discount.",
        customer_name="Verification Customer",
        decision_type=DecisionType.DISCOUNT_APPROVAL
    )

    try:
        trace = await decision_engine.construct_decision_trace(request)
        print(f"Decision trace created: {trace.decision_id}")
        
        # Try to save to Neo4j
        print("Attempting to save to Neo4j...")
        saved = await save_decision_trace(trace)
        
        if saved:
            print(f"SUCCESS: Decision {trace.decision_id} saved to Neo4j.")
        else:
            print(f"FAILURE: Decision {trace.decision_id} was NOT saved to Neo4j.")
            
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ingestion())
