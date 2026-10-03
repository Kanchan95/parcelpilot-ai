"""
Loads ParcelPilot_Data.xlsx into a local SQLite database at DB_PATH.
Run once: python -m ingestion.excel_ingester

Real Excel sheet names and columns:
  accounts : account_id, account_name, plan, status, csm, contract_file,
             premium_support, notes
  orders   : order_id, account_id, carrier, status, booked_at,
             pickup_window_start, pickup_window_end, pickup_actual_at,
             shipment_fee_inr, carrier_fault, customer_fault,
             cancellation_requested_at, notes
  tickets  : ticket_id, account_id, created_at, status, subject, description,
             channel, assigned_to, last_customer_message_at, historical_resolution
"""

import sqlite3
import pandas as pd
from pathlib import Path

import config

EXCEL_PATH = config.STRUCTURED_DIR / "ParcelPilot_Data.xlsx"

# Only the tables NOT loaded from Excel need explicit DDL.
# accounts / orders / tickets are created by pandas (if_exists="replace").
DDL_ONLY = """
CREATE TABLE IF NOT EXISTS actions_log (
    action_id    TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    session_id   TEXT,
    action_type  TEXT NOT NULL,
    parameters   TEXT,
    status       TEXT NOT NULL,
    executed_at  TEXT,
    executed_by  TEXT
);
"""


def _dt_to_str(df: pd.DataFrame) -> pd.DataFrame:
    """Convert all datetime columns to ISO strings (SQLite stores text)."""
    for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def _read_snapshot_time(xl: pd.ExcelFile) -> str | None:
    """
    Reads the snapshot time from the workbook's README sheet.
    All time-based calculations are relative to this
    value, NOT datetime.now().
    """
    readme_candidates = [s for s in xl.sheet_names if "readme" in s.lower()]
    if not readme_candidates:
        return None

    df = pd.read_excel(xl, sheet_name=readme_candidates[0], header=None)
    for row in df.itertuples(index=False):
        for cell in row:
            cell_str = str(cell).strip()
            # Accept values like "2026-08-16 11:00 Asia/Kolkata" or bare ISO dates
            if len(cell_str) >= 10 and cell_str[4] == "-" and cell_str[7] == "-":
                # Normalise: strip timezone label, keep datetime portion
                return cell_str.split(" Asia/")[0].split(" UTC")[0].strip()
    return None


def ingest_excel() -> None:
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(
            f"Excel file not found at {EXCEL_PATH}. "
            "Place ParcelPilot_Data.xlsx in data/structured/"
        )

    xl = pd.ExcelFile(EXCEL_PATH)

    # ── Persist snapshot time ─────────────────────────────────────────────
    snapshot_time = _read_snapshot_time(xl)
    if snapshot_time:
        config.SNAPSHOT_TIME_FILE.write_text(snapshot_time)
        print(f"  [ok] Snapshot time: {snapshot_time}")
    else:
        print(f"  [warn] README sheet not found — using default: {config.get_snapshot_time()}")

    conn = sqlite3.connect(config.DB_PATH)
    try:
        # Create only the tables that Excel doesn't supply
        conn.executescript(DDL_ONLY)
        conn.commit()

        for sheet in ["accounts", "orders", "tickets"]:
            if sheet not in xl.sheet_names:
                print(f"  [skip] Sheet '{sheet}' not found")
                continue

            df = pd.read_excel(xl, sheet_name=sheet)
            df = _dt_to_str(df)
            df = df.where(pd.notna(df), None)

            # Accounts table: inject credit_balance so apply_credit works
            if sheet == "accounts" and "credit_balance" not in df.columns:
                df["credit_balance"] = 0.0

            # Boolean columns to 0/1 integers for clean SQLite storage
            for col in df.select_dtypes(include=["bool"]).columns:
                df[col] = df[col].astype(int)

            df.to_sql(sheet, conn, if_exists="replace", index=False)
            print(f"  [ok] {sheet} → {len(df)} rows")

    finally:
        conn.close()

    print(f"\nSQLite database ready at {config.DB_PATH}")


if __name__ == "__main__":
    print("Ingesting Excel data...")
    ingest_excel()
