# Context Graph Decision Engine

A passive observation system that captures organizational decision traces at execution time (not after-the-fact) and stores them for ground truth retrieval.

## What This System Does

**The Problem:**
```
Sales rep emails manager: "Can we approve 18% discount for MedTech?"
Manager replies: "Yes, approved at 15%"
↓
6 months later: "Why did we give them 15%?"
Result: No one remembers. No audit trail. Knowledge lost.
```

**Our Solution:**
```
Email detected → Extract decision details → Enrich with live data:
- CRM: $450K ARR, Enterprise tier
- Support: 3 SEV-1 incidents
- Finance: 32% margin
→ Store complete decision trace with full context
→ Perfect institutional memory forever
```

## Quick Start

### 1. Setup Environment

```bash
cd backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env`:
```env
# Gemini API (required for LLM extraction)
GEMINI_API_KEY=your_gemini_api_key_here

# Gmail API (optional - only needed for Gmail mode)
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json

# Neo4j (Part 2)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### 3. Get Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Click "Get API Key"
3. Create new API key
4. Add to `.env` as `GEMINI_API_KEY`

### 4. (Optional) Setup Gmail OAuth

Only needed if you want to fetch emails directly from Gmail:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or select existing
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop App)
5. Download as `credentials.json` to backend directory

### 5. Run the Server

```bash
uvicorn app.main:app --reload
```

API available at: http://localhost:8000

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Welcome + API overview |
| `/health` | GET | Health check (Gmail, Gemini, APIs) |
| `/decision/ingest` | POST | **Main endpoint** - Ingest decision from email |
| `/decision/{id}` | GET | Get decision trace by ID |
| `/decisions` | GET | List all decisions |
| `/gmail/search` | GET | Search Gmail (requires OAuth) |
| `/gmail/message/{id}` | GET | Get specific email |
| `/gmail/thread/{id}` | GET | Get email thread |
| `/policies` | GET | List all policy versions |
| `/policies/current` | GET | Get current policy |
| `/api/mock/crm/{customer}` | GET | Mock CRM data |
| `/api/mock/support/{customer}` | GET | Mock Support data |
| `/api/mock/finance/{customer}` | GET | Mock Finance data |
| `/api/mock/customers` | GET | List all mock customers |

## Testing

### Test 1: Health Check
```bash
curl http://localhost:8000/health
```

### Test 2: Mock APIs
```bash
# CRM
curl http://localhost:8000/api/mock/crm/MedTech%20Corp

# Support
curl http://localhost:8000/api/mock/support/MedTech%20Corp

# Finance
curl http://localhost:8000/api/mock/finance/MedTech%20Corp
```

### Test 3: List Policies
```bash
curl http://localhost:8000/policies
```

### Test 4: Decision Ingestion (Manual Mode)
```bash
curl -X POST http://localhost:8000/decision/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "email_thread": "From: john.sales@company.com\nTo: jane.manager@company.com\nSubject: Discount Request - MedTech Corp\nDate: 2026-01-31T16:25:00Z\n\nHi Jane,\n\nMedTech Corp is asking for 18% discount to renew. They have had 3 SEV-1 incidents this quarter and are threatening churn. ARR is around $450K.\n\nCan we approve?\n- John\n\n---\n\nFrom: jane.manager@company.com\nDate: 2026-01-31T16:30:00Z\n\nApproved at 15%. 18% is too high given our margin on this account.\n\n- Jane",
    "customer_name": "MedTech Corp"
  }'
```

**Expected Response:**
```json
{
  "decision_id": "dec_abc123...",
  "timestamp": "2026-01-31T16:30:00Z",
  "decision_type": "discount_approval",
  "request": {
    "customer": "MedTech Corp",
    "requested_action": "18%",
    "requestor_email": "john.sales@company.com"
  },
  "decision": {
    "outcome": "modified",
    "final_action": "15%",
    "decision_maker_email": "jane.manager@company.com"
  },
  "evidence": [
    {"source": "salesforce", "field": "arr", "value": 450000},
    {"source": "zendesk", "field": "sev1_tickets", "value": 3},
    {"source": "stripe", "field": "margin_percent", "value": 32}
  ],
  "exceptions": [
    {
      "exception_type": "exceeds_standard_limit",
      "description": "Discount 15% exceeds standard limit of 10%",
      "policy_limit": "10%",
      "actual_value": "15%"
    }
  ]
}
```

## Mock Customers

| Customer | Industry | ARR | SEV-1s | Margin | Notes |
|----------|----------|-----|--------|--------|-------|
| MedTech Corp | Healthcare | $450K | 3 | 32% | - |
| HealthTech Inc | Healthcare | $320K | 1 | 38% | - |
| BioPharm LLC | Biotech | $180K | 0 | 42% | - |
| FinServe Co | Finance | $620K | 2 | 28% | Payment issues |
| TechStartup XYZ | Tech | $45K | 0 | 55% | New customer |

## Policy Versions

**v3.1** (Jun 2025 - Dec 2025):
- Standard: 10%, Manager: 15%, VP: 20%

**v3.2** (Jan 2026 - Current):
- Standard: 10%, Manager: 15%, VP: 25% (increased)
- New: Enterprise Special up to 30% with CFO

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic data models
│   ├── mock_apis.py         # Mock CRM/Support/Finance
│   ├── policy_store.py      # Policy version management
│   ├── gmail_service.py     # Gmail API integration
│   ├── gemini_service.py    # Gemini LLM integration
│   └── decision_engine.py   # Core orchestration logic
├── credentials.json         # Gmail OAuth (not in git)
├── token.json              # Gmail token (auto-generated)
├── .env                    # Environment variables
├── .env.example            # Example env file
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
