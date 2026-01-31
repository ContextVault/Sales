# Sales Backend

Backend API for the Sales application.

## Setup

### 1. Create Virtual Environment

```bash
cd backend

# Create virtual environment
python3.11 -m venv venv

# Activate it
source venv/bin/activate  # On Mac/Linux
# OR
venv\Scripts\activate  # On Windows

# Verify Python version
python --version  # Should be 3.11+
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:
- **GMAIL_CREDENTIALS_PATH**: Path to your Gmail OAuth credentials JSON file
- **GMAIL_TOKEN_PATH**: Path where the OAuth token will be stored
- **GEMINI_API_KEY**: Your Google Gemini API key
- **NEO4J_URI**: Neo4j database connection URI
- **NEO4J_USER**: Neo4j username
- **NEO4J_PASSWORD**: Neo4j password

### 4. Set Up Gmail OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API
4. Create OAuth 2.0 credentials
5. Download the credentials JSON file and save it as `credentials.json` in the backend directory

### 5. Run the Application

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application entry point
│   ├── models.py         # Pydantic models
│   ├── mock_apis.py      # Mock API endpoints for testing
│   ├── policy_store.py   # Policy storage and management
│   ├── decision_engine.py # Decision logic engine
│   └── gmail_service.py  # Gmail API integration
├── tests/                # Test files
├── credentials.json      # Gmail OAuth credentials (not in git)
├── .env                  # Environment variables (not in git)
├── .env.example          # Example environment file
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
