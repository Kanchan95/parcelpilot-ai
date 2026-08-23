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
echo "→ Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# 4. .env check
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Created .env from template."
  echo "    Add your GROQ_API_KEY to .env before running the app."
  echo "    (Get a free key at https://console.groq.com)"
  echo ""
else
  echo "✓ .env exists"
fi

# 5. Ingest Excel → SQLite (loads the real assessment data pack)
echo "→ Loading assessment data into SQLite..."
$PYTHON -m ingestion.excel_ingester

# 6. Ingest documents → ChromaDB
echo "→ Ingesting policy documents into ChromaDB (downloads embedding model ~80 MB on first run)..."
$PYTHON -m ingestion.document_ingester

# 7. (Optional) Build the frontend if Node is available
if command -v npm &>/dev/null; then
  echo "→ Building React frontend..."
  cd web && npm install --silent && npm run build --silent && cd ..
  echo "✓ Frontend built (web/dist/)"
else
  echo "⚠️  npm not found — skipping frontend build."
  echo "    Install Node 18+ and run: cd web && npm install && npm run build"
fi

echo ""
echo "==================================================="
echo "  Setup complete!"
echo ""
echo "  Start the application (serves built frontend + API):"
echo "    source .venv/bin/activate"
echo "    python server.py"
echo "    → http://localhost:8080"
echo ""
echo "  For frontend hot-reload during development:"
echo "    Terminal 1: python server.py"
echo "    Terminal 2: cd web && npm run dev"
echo "    → http://localhost:3000"
echo ""
echo "  Run tests:"
echo "    pytest tests/ -v"
echo "==================================================="
