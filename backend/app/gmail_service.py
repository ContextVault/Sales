"""
Gmail Service - Gmail API Integration with OAuth 2.0

Handles authentication and email operations for decision trace ingestion.
Supports fetching individual messages, threads, and searching.
"""
import os
import base64
import email
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()
logger = logging.getLogger(__name__)

# Gmail API scopes - read-only access
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailService:
    """
    Gmail API service for fetching and parsing emails.
    
    Handles OAuth 2.0 authentication flow and provides methods for:
    - Fetching individual messages
    - Fetching entire threads (conversations)
    - Searching Gmail with queries
    - Parsing message content (headers + body)
    """
    
    def __init__(self):
        """Initialize Gmail service with paths from environment variables."""
        self._credentials_path = os.getenv(
            "GMAIL_CREDENTIALS_PATH", 
            "credentials.json"
        )
        self._token_path = os.getenv(
            "GMAIL_TOKEN_PATH", 
            "token.json"
        )
        self._service = None
        self._credentials: Optional[Credentials] = None
        self._authenticated = False
        
        logger.info(f"GmailService initialized (credentials: {self._credentials_path})")
    
    def authenticate(self) -> bool:
        """
        Authenticate with Gmail API using OAuth 2.0.
        
        Flow:
        1. Check for existing valid token
        2. If token exists but expired, refresh it
        3. If no token, run OAuth flow (opens browser)
        
        Returns:
            True if authentication successful
            
        Raises:
            FileNotFoundError: If credentials.json is missing
        """
        # Check for existing token
        if os.path.exists(self._token_path):
            logger.info("Found existing token, loading...")
            self._credentials = Credentials.from_authorized_user_file(
                self._token_path, SCOPES
            )
        
        # Check if credentials need refresh or creation
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                logger.info("Token expired, refreshing...")
                self._credentials.refresh(Request())
            else:
                # Need to run OAuth flow
                logger.info("No valid token, starting OAuth flow...")
                
                if not os.path.exists(self._credentials_path):
                    raise FileNotFoundError(
                        f"Gmail credentials not found at '{self._credentials_path}'. "
                        "Please download OAuth credentials from Google Cloud Console "
                        "and save as 'credentials.json' in the backend directory."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_path, SCOPES
                )
                self._credentials = flow.run_local_server(port=0)
            
            # Save token for future use
            with open(self._token_path, "w") as token_file:
                token_file.write(self._credentials.to_json())
            logger.info(f"Token saved to {self._token_path}")
        
        # Build Gmail service
        self._service = build("gmail", "v1", credentials=self._credentials)
        self._authenticated = True
        logger.info("Gmail authentication successful")
        
        return True
    
    def is_authenticated(self) -> bool:
        """Check if service is currently authenticated."""
        return self._authenticated and self._service is not None
    
    def _ensure_authenticated(self) -> None:
        """Ensure service is authenticated before API calls."""
        if not self.is_authenticated():
            self.authenticate()
    
    async def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single email message by ID.
        
        Args:
            message_id: The Gmail message ID
            
        Returns:
            Parsed message dict with id, thread_id, subject, sender,
            recipients, date, body, and labels. Returns None if not found.
        """
        self._ensure_authenticated()
        
        try:
            message = self._service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()
            
            return self._parse_message(message)
            
        except HttpError as e:
            logger.error(f"Failed to fetch message {message_id}: {e}")
            if e.resp.status == 404:
                return None
            raise
    
    async def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch an entire email thread (conversation).
        
        Args:
            thread_id: The Gmail thread ID
            
        Returns:
            Dict with thread_id and list of parsed messages
        """
        self._ensure_authenticated()
        
        try:
            thread = self._service.users().threads().get(
                userId="me",
                id=thread_id,
                format="full"
            ).execute()
            
            messages = []
            for msg in thread.get("messages", []):
                parsed = self._parse_message(msg)
                if parsed:
                    messages.append(parsed)
            
            return {
                "thread_id": thread_id,
                "message_count": len(messages),
                "messages": messages,
                "combined_text": self._combine_thread_text(messages)
            }
            
        except HttpError as e:
            logger.error(f"Failed to fetch thread {thread_id}: {e}")
            if e.resp.status == 404:
                return None
            raise
    
    async def search_messages(
        self, 
        query: str, 
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search Gmail with a query string.
        
        Args:
            query: Gmail search query (e.g., "subject:discount approval")
            max_results: Maximum number of results to return
            
        Returns:
            List of message summaries (id, thread_id, subject, sender, date, snippet)
        """
        self._ensure_authenticated()
        
        try:
            results = self._service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get("messages", [])
            
            # Fetch metadata for each message
            parsed_results = []
            for msg in messages:
                # Get message with metadata only (faster than full)
                message = self._service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Date"]
                ).execute()
                
                headers = {
                    h["name"]: h["value"] 
                    for h in message.get("payload", {}).get("headers", [])
                }
                
                parsed_results.append({
                    "id": message["id"],
                    "thread_id": message["threadId"],
                    "subject": headers.get("Subject"),
                    "sender": headers.get("From"),
                    "date": headers.get("Date"),
                    "snippet": message.get("snippet", "")[:100]
                })
            
            return parsed_results
            
        except HttpError as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise
    
    def _parse_message(self, message: Dict) -> Dict[str, Any]:
        """
        Parse raw Gmail API message into structured format.
        
        Extracts:
        - Headers (From, To, Subject, Date)
        - Plain text body (from MIME parts)
        - Labels
        """
        headers = {}
        for header in message.get("payload", {}).get("headers", []):
            headers[header["name"].lower()] = header["value"]
        
        # Parse date to datetime
        date_str = headers.get("date")
        parsed_date = None
        if date_str:
            try:
                # Parse email date format
                parsed_date = email.utils.parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse date: {date_str}")
        
        # Extract body text
        body = self._extract_body(message.get("payload", {}))
        
        # Parse recipients
        recipients = []
        to_header = headers.get("to", "")
        if to_header:
            # Simple split - could be more robust for complex To headers
            recipients = [r.strip() for r in to_header.split(",")]
        
        return {
            "id": message["id"],
            "thread_id": message["threadId"],
            "subject": headers.get("subject"),
            "sender": headers.get("from"),
            "recipients": recipients,
            "date": parsed_date,
            "body": body,
            "labels": message.get("labelIds", []),
            "snippet": message.get("snippet", "")
        }
    
    def _extract_body(self, payload: Dict) -> str:
        """
        Extract plain text body from email payload.
        
        Handles multipart messages by finding text/plain parts.
        Falls back to text/html if no plain text available.
        """
        body_text = ""
        
        # Check for direct body data
        if "body" in payload and "data" in payload["body"]:
            body_data = payload["body"]["data"]
            body_text = self._decode_base64(body_data)
        
        # Check for multipart message
        elif "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                
                # Prefer text/plain
                if mime_type == "text/plain":
                    if "body" in part and "data" in part["body"]:
                        body_text = self._decode_base64(part["body"]["data"])
                        break
                
                # Recurse into nested multipart
                elif mime_type.startswith("multipart/"):
                    body_text = self._extract_body(part)
                    if body_text:
                        break
            
            # Fall back to text/html if no plain text
            if not body_text:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/html":
                        if "body" in part and "data" in part["body"]:
                            body_text = self._decode_base64(part["body"]["data"])
                            # Strip HTML tags (basic cleanup)
                            import re
                            body_text = re.sub(r"<[^>]+>", "", body_text)
                            break
        
        return body_text.strip()
    
    def _decode_base64(self, data: str) -> str:
        """Decode base64url-encoded email body data."""
        try:
            # Gmail uses URL-safe base64
            decoded = base64.urlsafe_b64decode(data)
            return decoded.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to decode body: {e}")
            return ""
    
    def _combine_thread_text(self, messages: List[Dict]) -> str:
        """
        Combine all messages in a thread into a single text block.
        
        Formats each message with From/Date headers, useful for
        LLM processing of entire conversations.
        """
        combined = []
        
        for msg in messages:
            date_str = ""
            if msg.get("date"):
                date_str = msg["date"].isoformat() if isinstance(msg["date"], datetime) else str(msg["date"])
            
            combined.append(
                f"From: {msg.get('sender', 'Unknown')}\n"
                f"Date: {date_str}\n"
                f"Subject: {msg.get('subject', '')}\n"
                f"\n{msg.get('body', '')}\n"
                f"\n---\n"
            )
        
        return "\n".join(combined)
    
    def check_connection(self) -> Dict[str, Any]:
        """
        Check Gmail connection status.
        
        Returns:
            Dict with connection status and details
        """
        result = {
            "connected": False,
            "credentials_exist": os.path.exists(self._credentials_path),
            "token_exists": os.path.exists(self._token_path),
            "authenticated": self._authenticated,
            "message": ""
        }
        
        if not result["credentials_exist"]:
            result["message"] = "credentials.json not found"
            return result
        
        if not result["token_exists"]:
            result["message"] = "Not authenticated - OAuth required"
            return result
        
        try:
            self.authenticate()
            # Try a simple API call to verify connection
            self._service.users().getProfile(userId="me").execute()
            result["connected"] = True
            result["message"] = "Connected to Gmail"
        except Exception as e:
            result["message"] = f"Connection failed: {str(e)}"
        
        return result


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

gmail_service = GmailService()
