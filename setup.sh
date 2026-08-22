#!/usr/bin/env bash
# One-time setup script for ParcelPilot AI.
# Run from the project root: bash setup.sh

set -e

echo ""
echo "==================================================="
echo "  ParcelPilot AI — Setup"
echo "==================================================="
echo ""

# 1. Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.10+ first."
  exit 1
fi
PYTHON=$(command -v python3)
echo "✓ Python: $($PYTHON --version)"

# 2. Virtual environment
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  $PYTHON -m venv .venv
fi
source .venv/bin/activate
echo "✓ Virtual environment active"

# 3. Install dependencies
echo "→ Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# 4. .env check
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Created .env from template."
  echo "    Add your ANTHROPIC_API_KEY to .env before running the app."
  echo ""
else
  echo "✓ .env exists"
fi

# 5. Generate mock Excel data
echo "→ Generating mock data (accounts, orders, tickets)..."
$PYTHON scripts/generate_mock_data.py

# 6. Ingest Excel → SQLite
echo "→ Loading data into SQLite..."
$PYTHON -m ingestion.excel_ingester

# 7. Ingest documents → ChromaDB (downloads embedding model ~80MB on first run)
echo "→ Ingesting documents into ChromaDB (may download embedding model on first run)..."
$PYTHON -m ingestion.document_ingester

echo ""
echo "==================================================="
echo "  Setup complete!"
echo ""
echo "  To run the app:"
echo "    source .venv/bin/activate"
echo "    streamlit run ui/app.py"
echo ""
echo "  To run the API (optional):"
echo "    uvicorn api.main:app --reload"
echo ""
echo "  To run tests:"
echo "    pytest tests/ -v"
echo "==================================================="
