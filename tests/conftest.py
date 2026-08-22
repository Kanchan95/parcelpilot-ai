"""
Pytest configuration: ensures the database and ChromaDB are populated
before any tests run. If setup hasn't been done, runs it automatically.
"""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path regardless of where pytest is invoked from
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    """Auto-run data setup if the DB doesn't exist yet."""
    import config as app_config

    if not app_config.DB_PATH.exists():
        print("\n[conftest] DB not found — running setup...")
        _run_setup(app_config)


def _run_setup(app_config):
    from scripts.generate_mock_data import main as gen_data
    from ingestion.excel_ingester import ingest_excel

    gen_data()
    ingest_excel()
    print("[conftest] DB ready.")
