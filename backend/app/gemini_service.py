"""
Gemini Service - LLM Integration for Email Parsing

Uses Google Gemini 1.5 Pro to extract structured decision data from
email threads. Configured for deterministic extraction with JSON output.
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Model configuration for deterministic extraction
GEMINI_MODEL = "gemini-3-flash-preview"
GENERATION_CONFIG = {
    "temperature": 0.1,         # Low temperature for consistent extraction
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2000,
}


# =============================================================================
# EXTRACTION PROMPT
# =============================================================================

DECISION_EXTRACTION_PROMPT = """You are an expert at extracting structured decision data from business email threads.

Analyze the following email thread about a {decision_type} for customer "{customer_name}".

EMAIL THREAD:
---
{email_text}
---

Extract the decision details and return a JSON object with the following structure:

{{
    "requested_discount": "string - the discount percentage requested (e.g., '18%')",
    "final_discount": "string - the discount percentage approved/denied (e.g., '15%')",
    "outcome": "string - one of: 'approved', 'rejected', 'modified', 'escalated', 'pending'",
    "requestor_email": "string - email address of person who made the request",
    "requestor_name": "string - name of requestor if available",
    "decision_maker_email": "string - email address of person who made the decision",
    "decision_maker_name": "string - name of decision maker if available",
    "request_timestamp": "string - ISO 8601 timestamp when request was made (or null)",
    "decision_timestamp": "string - ISO 8601 timestamp when decision was made (or null)",
    "reason": "string - why the request was made (customer's justification)",
    "reasoning": "string - explanation for the final decision"
}}

IMPORTANT RULES:
1. Extract exact values from the email - do not invent data
2. If a value is not found in the email, use null
3. For timestamps, extract from email headers or "Date:" lines, convert to ISO 8601 format
4. For email addresses, look in From:/To: headers or email signatures
5. If the approval was modified (different % than requested), outcome should be "modified"
6. Extract both the request reason AND the decision reasoning separately

Return ONLY the JSON object, no additional text or markdown formatting."""


# =============================================================================
# GEMINI SERVICE CLASS
# =============================================================================

class GeminiService:
    """
    Gemini LLM service for extracting structured data from emails.
    
    Provides deterministic extraction of decision details including:
    - Discount percentages (requested and final)
    - Decision outcome
    - Participants (requestor, decision maker)
    - Timestamps
    - Reasoning
    """
    
    def __init__(self):
        """Initialize Gemini client with API key."""
        self._api_key = os.getenv("GEMINI_API_KEY")
        self._model = None
        self._initialized = False
        
        if self._api_key:
            self._initialize()
        else:
            logger.warning("GEMINI_API_KEY not set - LLM extraction will not work")
    
    def _initialize(self) -> None:
        """Configure Gemini client and model."""
        try:
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config=GENERATION_CONFIG
            )
            self._initialized = True
            logger.info(f"Gemini service initialized with model {GEMINI_MODEL}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self._initialized = False
    
    def is_available(self) -> bool:
        """Check if Gemini service is available."""
        return self._initialized and self._model is not None
    
    async def extract_decision_from_email(
        self,
        email_text: str,
        customer_name: str,
        decision_type: str = "discount_approval"
    ) -> Dict[str, Any]:
        """
        Extract structured decision data from an email thread.
        
        Args:
            email_text: The raw email thread text
            customer_name: Name of the customer involved
            decision_type: Type of decision (default: discount_approval)
            
        Returns:
            Dict with extracted decision fields:
            - requested_discount
            - final_discount
            - outcome
            - requestor_email, requestor_name
            - decision_maker_email, decision_maker_name
            - request_timestamp, decision_timestamp
            - reason, reasoning
            
        Raises:
            ValueError: If Gemini is not configured
            RuntimeError: If extraction fails
        """
        if not self.is_available():
            raise ValueError(
                "Gemini service not available. "
                "Please set GEMINI_API_KEY in environment variables."
            )
        
        # Build prompt
        prompt = DECISION_EXTRACTION_PROMPT.format(
            decision_type=decision_type,
            customer_name=customer_name,
            email_text=email_text
        )
        
        try:
            # Call Gemini
            response = self._model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse JSON response
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                # Remove markdown code block markers
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])
            
            extracted_data = json.loads(response_text)
            
            # Add metadata
            extracted_data["_extraction_metadata"] = {
                "model": GEMINI_MODEL,
                "extracted_at": datetime.utcnow().isoformat(),
                "customer_name": customer_name
            }
            
            logger.info(f"Successfully extracted decision data for {customer_name}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.error(f"Raw response: {response_text[:500]}")
            raise RuntimeError(f"LLM extraction failed: Invalid JSON response")
            
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            raise RuntimeError(f"LLM extraction failed: {str(e)}")
    
    async def extract_with_fallback(
        self,
        email_text: str,
        customer_name: str,
        decision_type: str = "discount_approval"
    ) -> Dict[str, Any]:
        """
        Extract decision data with fallback for when Gemini is unavailable.
        
        If Gemini is not available or fails, returns a partial extraction
        based on simple pattern matching. This allows the system to work
        (with reduced accuracy) even without LLM.
        
        Args:
            email_text: The raw email thread text
            customer_name: Name of the customer involved
            decision_type: Type of decision
            
        Returns:
            Dict with extracted (or partially extracted) decision fields
        """
        if self.is_available():
            try:
                return await self.extract_decision_from_email(
                    email_text, customer_name, decision_type
                )
            except Exception as e:
                logger.warning(f"Gemini extraction failed, using fallback: {e}")
        
        # Fallback: Simple pattern-based extraction
        return self._fallback_extraction(email_text, customer_name)
    
    def _fallback_extraction(
        self, 
        email_text: str, 
        customer_name: str
    ) -> Dict[str, Any]:
        """
        Simple pattern-based extraction fallback.
        
        Used when Gemini is unavailable. Provides partial extraction
        based on common email patterns.
        """
        import re
        
        result = {
            "requested_discount": None,
            "final_discount": None,
            "outcome": "pending",
            "requestor_email": None,
            "requestor_name": None,
            "decision_maker_email": None,
            "decision_maker_name": None,
            "request_timestamp": None,
            "decision_timestamp": None,
            "reason": None,
            "reasoning": None,
            "_extraction_metadata": {
                "model": "fallback_regex",
                "extracted_at": datetime.utcnow().isoformat(),
                "customer_name": customer_name,
                "warning": "Gemini unavailable - used pattern matching"
            }
        }
        
        # Extract email addresses
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', email_text)
        if len(emails) >= 1:
            result["requestor_email"] = emails[0]
        if len(emails) >= 2:
            result["decision_maker_email"] = emails[1]
        
        # Extract percentages
        percentages = re.findall(r'(\d{1,2})%', email_text)
        if len(percentages) >= 1:
            result["requested_discount"] = f"{percentages[0]}%"
        if len(percentages) >= 2:
            result["final_discount"] = f"{percentages[-1]}%"
        
        # Detect approval
        email_lower = email_text.lower()
        if "approved" in email_lower or "approve" in email_lower:
            result["outcome"] = "approved"
            if result["requested_discount"] != result["final_discount"]:
                result["outcome"] = "modified"
        elif "rejected" in email_lower or "denied" in email_lower:
            result["outcome"] = "rejected"
        
        return result
    
    def check_status(self) -> Dict[str, Any]:
        """
        Check Gemini service status.
        
        Returns:
            Dict with availability status and details
        """
        return {
            "available": self.is_available(),
            "api_key_set": bool(self._api_key),
            "model": GEMINI_MODEL if self.is_available() else None,
            "message": "Ready" if self.is_available() else "GEMINI_API_KEY not configured"
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

gemini_service = GeminiService()


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

async def extract_decision_from_email(
    email_text: str,
    customer_name: str,
    decision_type: str = "discount_approval"
) -> Dict[str, Any]:
    """Convenience function for decision extraction."""
    return await gemini_service.extract_with_fallback(
        email_text, customer_name, decision_type
    )
