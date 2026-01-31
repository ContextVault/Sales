"""
Gmail Monitor Service - Real-time Gmail Email Monitoring and Ingestion

Provides functionality to:
- Search Gmail for decision-related emails
- Track processed messages to avoid duplicates
- Ingest single or batch emails into the decision engine
- Store decision traces in Neo4j
"""
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.gmail_service import gmail_service
from app.decision_engine import decision_engine
from app.graph_operations import save_decision_trace
from app.models import EmailIngestionRequest, DecisionType

logger = logging.getLogger(__name__)


class GmailMonitor:
    """
    Gmail monitoring service for real-time email ingestion.
    
    Tracks processed messages to avoid re-processing and provides
    methods for single and batch email ingestion.
    """
    
    def __init__(self):
        """Initialize Gmail monitor with empty processed set."""
        self.processed_message_ids: set = set()
        self.last_check_time: Optional[datetime] = None
        logger.info("Gmail Monitor initialized")
    
    async def search_decision_emails(
        self,
        query: str = "subject:(discount OR approval)",
        max_results: int = 10
    ) -> List[Dict]:
        """
        Search Gmail for decision-related emails.
        
        Args:
            query: Gmail search query string
            max_results: Maximum number of results to return
            
        Returns:
            List of message dicts with id, thread_id, subject, from, date, snippet
        """
        try:
            self.last_check_time = datetime.utcnow()
            messages = await gmail_service.search_messages(query, max_results)
            
            if not messages:
                logger.info(f"No messages found for query: {query}")
                return []
            
            logger.info(f"Found {len(messages)} messages for query: {query}")
            return messages
            
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}")
            return []
    
    async def get_unprocessed_emails(
        self,
        query: str = "subject:(discount OR approval)",
        max_results: int = 20
    ) -> List[Dict]:
        """
        Get decision emails that haven't been processed yet.
        
        Args:
            query: Gmail search query string
            max_results: Maximum number of results to search
            
        Returns:
            List of unprocessed message dicts
        """
        all_messages = await self.search_decision_emails(query, max_results)
        
        unprocessed = [
            msg for msg in all_messages
            if msg.get('id') not in self.processed_message_ids
        ]
        
        logger.info(
            f"Found {len(unprocessed)} unprocessed emails "
            f"(out of {len(all_messages)} total)"
        )
        return unprocessed
    
    def _extract_customer_from_subject(self, subject: str) -> str:
        """
        Extract customer name from email subject.
        
        Patterns matched:
        - "Discount Request - MedTech Corp" -> "MedTech Corp"
        - "Approval Request: HealthTech Inc" -> "HealthTech Inc"
        - Any other format -> "Unknown Customer"
        
        Args:
            subject: Email subject line
            
        Returns:
            Extracted customer name or "Unknown Customer"
        """
        if not subject:
            return "Unknown Customer"
        
        # Pattern: "Something - CustomerName"
        if ' - ' in subject:
            parts = subject.split(' - ')
            if len(parts) >= 2:
                return parts[-1].strip()
        
        # Pattern: "Something: CustomerName"
        if ': ' in subject:
            parts = subject.split(': ')
            if len(parts) >= 2:
                return parts[-1].strip()
        
        # Pattern: "for CustomerName"
        match = re.search(r'\bfor\s+([A-Z][A-Za-z\s]+(?:Corp|Inc|LLC|Ltd|Co)?)', subject)
        if match:
            return match.group(1).strip()
        
        return "Unknown Customer"
    
    async def ingest_email(
        self,
        message_id: str,
        customer_name: str,
        auto_save: bool = True
    ) -> Dict[str, Any]:
        """
        Ingest a single email and create decision trace.
        
        Steps:
        1. Check if already processed
        2. Fetch email thread from Gmail
        3. Construct decision trace using existing decision_engine
        4. Save to Neo4j if auto_save is True
        5. Mark message_id as processed
        
        Args:
            message_id: Gmail message ID to ingest
            customer_name: Customer name for the decision
            auto_save: Whether to save to Neo4j automatically
            
        Returns:
            Dict with success status, decision_id, trace, and any errors
        """
        # Check if already processed
        if message_id in self.processed_message_ids:
            logger.warning(f"Message {message_id} already processed, skipping")
            return {
                "success": False,
                "error": "Message already processed",
                "message_id": message_id
            }
        
        try:
            # Get the message to find thread ID
            message = await gmail_service.get_message(message_id)
            if not message:
                return {
                    "success": False,
                    "error": f"Message {message_id} not found",
                    "message_id": message_id
                }
            
            thread_id = message.get('thread_id')
            
            # Create ingestion request using gmail_thread_id for full conversation
            request = EmailIngestionRequest(
                gmail_thread_id=thread_id,
                customer_name=customer_name,
                decision_type=DecisionType.DISCOUNT_APPROVAL
            )
            
            # Construct decision trace using existing engine
            logger.info(f"Constructing decision trace for message {message_id}")
            trace = await decision_engine.construct_decision_trace(request)
            
            # Save to Neo4j if requested
            if auto_save:
                logger.info(f"Saving decision trace {trace.decision_id} to Neo4j")
                saved = await save_decision_trace(trace)
                if not saved:
                    logger.warning(
                        f"Failed to save trace {trace.decision_id} to Neo4j"
                    )
            
            # Mark as processed
            self.processed_message_ids.add(message_id)
            
            logger.info(
                f"Successfully ingested message {message_id} "
                f"as decision {trace.decision_id}"
            )
            
            return {
                "success": True,
                "message_id": message_id,
                "decision_id": trace.decision_id,
                "trace": trace,
                "saved_to_neo4j": auto_save
            }
            
        except Exception as e:
            logger.error(f"Error ingesting message {message_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message_id": message_id
            }
    
    async def batch_ingest(
        self,
        query: str = "subject:(discount OR approval)",
        customer_name: Optional[str] = None,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        Search Gmail and ingest multiple emails at once.
        
        If customer_name not provided, attempts to extract from subject line.
        
        Args:
            query: Gmail search query string
            customer_name: Optional customer name (if None, extracted from subject)
            max_results: Maximum number of emails to process
            
        Returns:
            Dict with total count, successful count, failed count, and results list
        """
        logger.info(f"Starting batch ingest with query: {query}")
        
        # Get unprocessed emails
        messages = await self.get_unprocessed_emails(query, max_results)
        
        if not messages:
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "results": [],
                "message": "No unprocessed emails found"
            }
        
        results = []
        successful = 0
        failed = 0
        
        for msg in messages:
            # Determine customer name
            if customer_name:
                cust = customer_name
            else:
                cust = self._extract_customer_from_subject(
                    msg.get('subject', '')
                )
            
            # Ingest the email
            result = await self.ingest_email(
                message_id=msg['id'],
                customer_name=cust,
                auto_save=True
            )
            
            results.append({
                "message_id": msg['id'],
                "subject": msg.get('subject'),
                "customer": cust,
                "success": result['success'],
                "decision_id": result.get('decision_id'),
                "error": result.get('error')
            })
            
            if result['success']:
                successful += 1
            else:
                failed += 1
        
        logger.info(
            f"Batch ingest complete: {successful} successful, {failed} failed"
        )
        
        return {
            "total": len(messages),
            "successful": successful,
            "failed": failed,
            "results": results
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get Gmail monitoring statistics.
        
        Returns:
            Dict with processed count, last check time, etc.
        """
        return {
            "processed_count": len(self.processed_message_ids),
            "processed_message_ids": list(self.processed_message_ids),
            "last_check_time": (
                self.last_check_time.isoformat()
                if self.last_check_time else None
            )
        }
    
    def reset_processed(self):
        """Clear the processed message IDs set."""
        count = len(self.processed_message_ids)
        self.processed_message_ids.clear()
        logger.info(f"Reset processed messages, cleared {count} IDs")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

gmail_monitor = GmailMonitor()
