"""
Pytest configuration: ensures the SQLite database is populated before any tests
run, and redirects all DB operations to an isolated temp copy so the real
parcelpilot.db is never mutated by the test suite.
"""

import shutil
import sys
from pathlib import Path

import pytest


# Ensure project root is on sys.path regardless of where pytest is invoked from
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    """Register custom marks and auto-run data setup if the DB doesn't exist yet."""
    config.addinivalue_line(
        "markers", "chroma: mark test as requiring ChromaDB to be populated"
    )
    import config as app_config
    if not app_config.DB_PATH.exists():
        print("\n[conftest] DB not found — running setup...")
        _run_setup(app_config)


def _run_setup(app_config):
    from ingestion.excel_ingester import ingest_excel
    ingest_excel()
    print("[conftest] DB ready (loaded from ParcelPilot_Assessment_Data.xlsx).")


@pytest.fixture(scope="session", autouse=True)
def isolated_test_db(tmp_path_factory):
    """
    Redirect all DB operations to a temporary copy of parcelpilot.db.

    Every tool (action_executor, structured_lookup, issue_detector) accesses
    the DB via config.DB_PATH at call time — never cached at import. Patching
    that attribute here redirects all reads and writes to the temp copy so the
    real application database is never opened or mutated during tests.

    The temp copy is discarded after the session; the real DB is untouched.
    """
    import config as app_config

    real_path = app_config.DB_PATH
    tmp_dir = tmp_path_factory.mktemp("testdb")
    test_path = tmp_dir / "parcelpilot_test.db"
    shutil.copy2(real_path, test_path)

    app_config.DB_PATH = test_path
    yield test_path
    app_config.DB_PATH = real_path
