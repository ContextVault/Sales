"""
Gemini Service - Enhanced LLM Integration for Email Parsing

Uses Google Gemini to extract structured decision data from email threads.
Part 3 enhancements:
- Confidence scoring for extractions
- Semantic embeddings generation
- Similarity calculation between decisions
- Natural language similarity explanations
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
import google.generativeai as genai
import numpy as np

load_dotenv()
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Model configuration for deterministic extraction
GEMINI_MODEL = "gemini-2.5-flash"
GENERATION_CONFIG = {
    "temperature": 0.1,         # Low temperature for consistent extraction
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2000,
}

# Embedding model for semantic similarity
EMBEDDING_MODEL = "models/text-embedding-004"


# =============================================================================
# ENHANCED EXTRACTION PROMPT
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
    "reasoning": "string - explanation for the final decision",
    "confidence": {{
        "requested_discount": 0.95,
        "final_discount": 0.90,
        "outcome": 0.98,
        "requestor_email": 1.0,
        "decision_maker_email": 1.0,
        "timestamps": 0.7,
        "reason": 0.85,
        "reasoning": 0.90
    }},
    "notes": "string - any additional observations about the decision"
}}

IMPORTANT RULES:
1. Extract exact values from the email - do not invent data
2. If a value is not found in the email, use null
3. For timestamps, extract from email headers or "Date:" lines, convert to ISO 8601 format
4. For email addresses, look in From:/To: headers or email signatures
5. If the approval was modified (different % than requested), outcome should be "modified"
6. Extract both the request reason AND the decision reasoning separately

HANDLING AMBIGUOUS LANGUAGE:
- "ok", "LGTM", "go ahead", "fine by me", "sounds good" = approved
- "approved", "yes", "approve", "confirmed" = approved
- "no", "reject", "denied", "too high", "can't do that" = rejected (unless followed by counter-offer)
- If decision maker offers lower discount (e.g., "18% is too high, approve at 15%"), that's "modified" at the lower amount
- If multiple people discuss but one makes final call, use the final decision maker
- Percentages might be written as "15 percent", "15%", or "fifteen percent" - normalize to "15%"

CONFIDENCE SCORES (0.0 to 1.0):
- 1.0 = Explicitly stated in email, completely clear
- 0.8-0.9 = Strongly implied, clear context
- 0.6-0.7 = Inferred from limited context
- <0.6 = Guessed or unclear

Return ONLY the JSON object, no additional text or markdown formatting."""


# =============================================================================
# GEMINI SERVICE CLASS
# =============================================================================

class GeminiService:
    """
    Enhanced Gemini LLM service for extracting structured data from emails.
    
    Part 3 capabilities:
    - Extract decision details with confidence scores
    - Generate text embeddings for semantic similarity
    - Calculate similarity between decision contexts
    - Generate natural language similarity explanations
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
        Extract structured decision data from an email thread with confidence scores.
        
        Args:
            email_text: The raw email thread text
            customer_name: Name of the customer involved
            decision_type: Type of decision (default: discount_approval)
            
        Returns:
            Dict with extracted decision fields including:
            - requested_discount, final_discount
            - outcome (approved/rejected/modified/escalated/pending)
            - requestor_email, requestor_name
            - decision_maker_email, decision_maker_name
            - request_timestamp, decision_timestamp
            - reason, reasoning
            - confidence (per-field confidence scores)
            
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
            if response_text.startswith("```json"):
                response_text = response_text[7:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
            
            response_text = response_text.strip()
            extracted_data = json.loads(response_text)
            
            # Validate and normalize
            extracted_data = self._validate_and_normalize(extracted_data)
            
            # Add metadata
            extracted_data["_extraction_metadata"] = {
                "model": GEMINI_MODEL,
                "extracted_at": datetime.utcnow().isoformat(),
                "customer_name": customer_name
            }
            
            # Log confidence
            if "confidence" in extracted_data:
                avg_confidence = sum(extracted_data["confidence"].values()) / len(extracted_data["confidence"])
                logger.info(f"Extraction confidence for {customer_name}: {avg_confidence:.2f}")
                if avg_confidence < 0.7:
                    logger.warning(f"Low confidence extraction for {customer_name}")
            
            logger.info(f"Successfully extracted decision data for {customer_name}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.error(f"Raw response: {response_text[:500]}")
            raise RuntimeError(f"LLM extraction failed: Invalid JSON response")
            
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            raise RuntimeError(f"LLM extraction failed: {str(e)}")
    
    def _validate_and_normalize(self, extracted_data: Dict) -> Dict:
        """
        Validate and normalize extracted data.
        
        - Ensure percentages are formatted consistently
        - Parse timestamps
        - Validate email addresses
        - Set defaults for missing fields
        """
        import re
        from dateutil import parser as date_parser
        
        # Normalize percentages
        for field in ['requested_discount', 'final_discount']:
            if field in extracted_data and extracted_data[field]:
                value = str(extracted_data[field])
                # Extract numbers and add %
                numbers = re.findall(r'\d+(?:\.\d+)?', value)
                if numbers:
                    extracted_data[field] = f"{numbers[0]}%"
        
        # Parse timestamps
        for field in ['request_timestamp', 'decision_timestamp']:
            if field in extracted_data and extracted_data[field]:
                value = extracted_data[field]
                if isinstance(value, str):
                    try:
                        # Try parsing ISO format or various date formats
                        parsed_date = date_parser.parse(value)
                        extracted_data[field] = parsed_date.isoformat()
                    except Exception:
                        # If parsing fails, use current time
                        logger.warning(f"Could not parse timestamp {value}, using current time")
                        extracted_data[field] = datetime.utcnow().isoformat()
        
        # Validate outcome
        if 'outcome' in extracted_data:
            outcome = str(extracted_data['outcome']).lower()
            valid_outcomes = ['approved', 'rejected', 'modified', 'escalated', 'pending']
            if outcome not in valid_outcomes:
                logger.warning(f"Invalid outcome '{outcome}', defaulting to 'pending'")
                extracted_data['outcome'] = 'pending'
            else:
                extracted_data['outcome'] = outcome
        
        # Ensure confidence dict exists
        if 'confidence' not in extracted_data:
            extracted_data['confidence'] = {
                'overall': 0.7  # Default medium confidence
            }
        
        return extracted_data
    
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
            "confidence": {
                "overall": 0.3  # Low confidence for fallback
            },
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
            result["decision_maker_email"] = emails[-1]
        
        # Extract percentages
        percentages = re.findall(r'(\d{1,2})%', email_text)
        if len(percentages) >= 1:
            result["requested_discount"] = f"{percentages[0]}%"
        if len(percentages) >= 2:
            result["final_discount"] = f"{percentages[-1]}%"
        elif len(percentages) == 1:
            result["final_discount"] = f"{percentages[0]}%"
        
        # Detect approval patterns
        email_lower = email_text.lower()
        approval_patterns = ["approved", "approve", "lgtm", "ok", "go ahead", "sounds good", "fine by me"]
        rejection_patterns = ["rejected", "denied", "no", "can't do", "too high"]
        
        if any(p in email_lower for p in approval_patterns):
            result["outcome"] = "approved"
            if result["requested_discount"] != result["final_discount"]:
                result["outcome"] = "modified"
        elif any(p in email_lower for p in rejection_patterns):
            result["outcome"] = "rejected"
        
        return result
    
    # =========================================================================
    # PART 3: SEMANTIC SIMILARITY FUNCTIONS
    # =========================================================================
    
    async def generate_embeddings(self, text: str) -> List[float]:
        """
        Generate embeddings for semantic similarity.
        
        Used for precedent matching - finding decisions with similar context
        even if exact keywords don't match.
        
        Args:
            text: Text to generate embeddings for
            
        Returns:
            List of floats representing the embedding vector
        """
        if not self.is_available():
            logger.warning("Gemini not available for embeddings")
            return []
        
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return []
    
    async def calculate_similarity(
        self,
        decision_text: str,
        precedent_text: str
    ) -> float:
        """
        Calculate semantic similarity between two decisions.
        
        Uses cosine similarity of embeddings.
        
        Args:
            decision_text: Text summary of current decision
            precedent_text: Text summary of precedent decision
            
        Returns:
            Similarity score 0.0-1.0
        """
        try:
            # Generate embeddings
            decision_embedding = await self.generate_embeddings(decision_text)
            precedent_embedding = await self.generate_embeddings(precedent_text)
            
            if not decision_embedding or not precedent_embedding:
                return 0.0
            
            # Calculate cosine similarity
            decision_vec = np.array(decision_embedding)
            precedent_vec = np.array(precedent_embedding)
            
            dot_product = np.dot(decision_vec, precedent_vec)
            norm_a = np.linalg.norm(decision_vec)
            norm_b = np.linalg.norm(precedent_vec)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            similarity = dot_product / (norm_a * norm_b)
            
            return float(similarity)
        
        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0
    
    async def explain_decision_similarity(
        self,
        decision_summary: str,
        precedent_summary: str,
        similarity_score: float
    ) -> str:
        """
        Generate natural language explanation of why two decisions are similar.
        
        Args:
            decision_summary: Summary of current decision
            precedent_summary: Summary of precedent decision
            similarity_score: Calculated similarity score
            
        Returns:
            Human-readable explanation of similarity
        """
        if not self.is_available():
            return f"Similar decision context (score: {similarity_score:.2f})"
        
        prompt = f"""Compare these two business decisions and explain WHY they are similar.

DECISION 1:
{decision_summary}

DECISION 2:
{precedent_summary}

SIMILARITY SCORE: {similarity_score:.2f} (0.0 = completely different, 1.0 = identical)

Generate a brief 1-2 sentence explanation of the key similarities.
Focus on: customer profile, business context, reasoning used.

Example: "Both involve enterprise healthcare customers with high ARR experiencing service quality issues that threatened contract renewal."

Your explanation:"""
        
        try:
            response = self._model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Failed to explain similarity: {e}")
            return f"Similar decision context (score: {similarity_score:.2f})"
    
    async def chat(self, prompt: str) -> str:
        """
        Generate a response from the LLM for a given prompt.
        
        Args:
            prompt: User prompt or system instruction
            
        Returns:
            Generated text response
        """
        if not self.is_available():
            raise ValueError("Gemini service not available")
            
        try:
            response = self._model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Chat generation failed: {e}")
            raise RuntimeError(f"Chat generation failed: {str(e)}")

    
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
            "embedding_model": EMBEDDING_MODEL if self.is_available() else None,
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
