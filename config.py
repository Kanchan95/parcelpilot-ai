from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "documents"
STRUCTURED_DIR = DATA_DIR / "structured"
CHROMA_DIR = BASE_DIR / ".chromadb"
DB_PATH = BASE_DIR / "parcelpilot.db"
SNAPSHOT_TIME_FILE = BASE_DIR / ".snapshot_time"

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))
COLLECTION_NAME: str = "parcelpilot_docs"
TOP_K_RETRIEVAL: int = int(os.getenv("TOP_K_RETRIEVAL", "12"))
TOP_K_RERANKED: int = int(os.getenv("TOP_K_RERANKED", "5"))

# CORS: allowed frontend origins.
# In production, set ALLOWED_ORIGINS to your deployed frontend URL.
# Multiple origins are separated by commas.
# Defaults cover Vite dev server (port 3000 per vite.config.ts), Vite's own
# default port (5173), and production mode where FastAPI serves the built SPA
# on the same port as the backend (8080).
ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:8080",
    ).split(",")
    if o.strip()
]


def get_snapshot_time() -> str:
    """
    Returns the dataset snapshot time as an ISO string.
    The Excel workbook's README sheet is the authoritative source.
    All time-based calculations (cancellation windows, SLA breaches, overdue orders)
    must be relative to this time, NOT datetime.now().
    Falls back to a stored value from the last ingestion if the file exists.
    """
    if SNAPSHOT_TIME_FILE.exists():
        return SNAPSHOT_TIME_FILE.read_text().strip()
    # Default used only if ingestion hasn't run yet
    return "2026-08-01 00:00:00"

# Authority weights used when re-ranking retrieved document chunks.
# Higher = more trusted. Customer agreements always beat general policy.
AUTHORITY_WEIGHTS: dict[str, float] = {
    "customer_agreement": 3.0,
    "current_policy": 2.0,
    "current_sop": 1.8,
    "product_guide": 1.6,
    "deprecated_policy": 0.4,
    "deprecated_sop": 0.3,
}

# Mock accounts used for auth in the demo.
DEMO_ACCOUNTS: dict[str, dict] = {
    "ACCT-001": {"company": "Northstar Logistics", "role": "customer"},
    "ACCT-002": {"company": "LumenWorks",          "role": "customer"},
    "ACCT-003": {"company": "Beacon Retail",       "role": "customer"},
    "ACCT-004": {"company": "Axis Labs",           "role": "customer"},
    "INTERNAL": {"company": "ParcelPilot Ops",     "role": "internal"},
}

# SLA first-response targets in minutes per plan and priority.
# Sourced from Support Policy v3 (Current).
SLA_MINUTES: dict[str, dict[str, int]] = {
    "Enterprise": {"P1": 30,  "P2": 120,  "P3": 480},
    "Growth":     {"P1": 120, "P2": 240,  "P3": 2880},
    "Standard":   {"P1": 240, "P2": 480,  "P3": 2880},
}

# Dataset snapshot time — overridden at runtime by excel_ingester reading
# the README sheet.  All time-based reasoning uses this value.
SNAPSHOT_TIME_DEFAULT = "2026-08-16 11:00:00"
