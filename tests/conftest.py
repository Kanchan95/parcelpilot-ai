"""
Pytest configuration: ensures the database and ChromaDB are populated
before any tests run. If setup hasn't been done, runs it automatically.
"""

import shutil
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
