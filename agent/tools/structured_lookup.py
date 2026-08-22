"""
Tool B — Structured Data Lookup

Queries the SQLite database (accounts, orders, tickets).
Access control is enforced at the SQL level: every query hard-filters by the
session's account_id. The LLM cannot bypass this — it never passes account_id
as a parameter; the tool injects it from the trusted session context.

Internal agents (account_id == "INTERNAL") may query any account but must
supply the target account_id as a lookup parameter.

Real schema columns:
  accounts : account_id, account_name, plan, status, csm, contract_file,
             premium_support, notes, credit_balance
  orders   : order_id, account_id, carrier, status, booked_at,
             pickup_window_start, pickup_window_end, pickup_actual_at,
             shipment_fee_inr, carrier_fault, customer_fault,
             cancellation_requested_at, notes
  tickets  : ticket_id, account_id, created_at, status, subject, description,
             channel, assigned_to, last_customer_message_at, historical_resolution
"""

import sqlite3
from contextlib import contextmanager
from typing import Any

import config
from agent.analysis import issue_detector


@contextmanager
def _db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _rows_to_list(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ── Public query functions ─────────────────────────────────────────────────────

def get_account_info(account_id: str, session_account_id: str, is_internal: bool) -> dict:
    """Returns account details. Customers may only query their own account."""
    target = account_id if is_internal else session_account_id
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (target,)
        ).fetchone()
    if row is None:
        return {"error": f"Account {target} not found or not accessible."}
    return _row_to_dict(row)


def get_order(order_id: str, session_account_id: str, is_internal: bool) -> dict:
    """
    Returns a single order.
    Customers: order must belong to their account (enforced by AND clause).
    Internal: can retrieve any order.
    """
    with _db() as conn:
        if is_internal:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? AND account_id = ?",
                (order_id, session_account_id),
            ).fetchone()

    if row is None:
        return {
            "error": (
                f"Order {order_id} not found or not accessible for this account. "
                "Orders from other accounts cannot be accessed."
            )
        }
    return _row_to_dict(row)


def list_orders(session_account_id: str, status_filter: str | None = None) -> dict:
    """Lists orders for the session account, optionally filtered by status."""
    with _db() as conn:
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM orders WHERE account_id = ? AND UPPER(status) = UPPER(?) ORDER BY booked_at DESC",
                (session_account_id, status_filter),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders WHERE account_id = ? ORDER BY booked_at DESC",
                (session_account_id,),
            ).fetchall()
    return {"orders": _rows_to_list(rows), "count": len(rows)}


def get_ticket(ticket_id: str, session_account_id: str, is_internal: bool) -> dict:
    """Returns a single ticket, scoped to the session account."""
    with _db() as conn:
        if is_internal:
            row = conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ? AND account_id = ?",
                (ticket_id, session_account_id),
            ).fetchone()
    if row is None:
        return {"error": f"Ticket {ticket_id} not found or not accessible."}
    result = _row_to_dict(row)
    if result and result.get("historical_resolution"):
        result["_historical_resolution_warning"] = (
            "Historical resolutions may contain incorrect information and should NOT be "
            "treated as current policy. Always verify against current policy documents."
        )
    return result


def list_tickets(
    session_account_id: str,
    is_internal: bool,
    target_account_id: str | None = None,
    status_filter: str | None = None,
    subject_filter: str | None = None,
) -> dict:
    """
    Lists tickets.
    - Customers: only their own tickets.
    - Internal agents: can specify target_account_id or leave None for all accounts.
    """
    account_filter = (
        target_account_id if (is_internal and target_account_id) else session_account_id
    )

    conditions = ["1=1"]
    params: list[Any] = []

    if not (is_internal and target_account_id is None):
        conditions.append("account_id = ?")
        params.append(account_filter)

    if status_filter:
        conditions.append("LOWER(status) = LOWER(?)")
        params.append(status_filter)

    if subject_filter:
        conditions.append("LOWER(subject) LIKE LOWER(?)")
        params.append(f"%{subject_filter}%")

    sql = f"SELECT * FROM tickets WHERE {' AND '.join(conditions)} ORDER BY created_at DESC"

    with _db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return {"tickets": _rows_to_list(rows), "count": len(rows)}


def get_credit_balance(session_account_id: str) -> dict:
    """Returns the current credit balance for the session account."""
    with _db() as conn:
        row = conn.execute(
            "SELECT account_id, account_name, credit_balance FROM accounts WHERE account_id = ?",
            (session_account_id,),
        ).fetchone()
    if row is None:
        return {"error": "Account not found."}
    return _row_to_dict(row)


def sla_breach_report(session_account_id: str, is_internal: bool) -> dict:
    """
    Computes SLA breach status for open tickets at dataset snapshot time.
    SLA first-response targets (from Support Policy v3):
      Enterprise P1=30min, P2=2hr, P3=8hr
      Growth     P1=2hr,  P2=4hr, P3=48hr
      Standard   P1=4hr,  P2=8hr, P3=48hr
    Priority is inferred from subject keywords since the ticket schema has no priority field.
    """
    snapshot = config.get_snapshot_time()  # "2026-08-16 11:00:00"

    with _db() as conn:
        if is_internal:
            rows = conn.execute(
                """
                SELECT t.ticket_id, t.account_id, a.account_name, a.plan,
                       t.status, t.subject, t.description, t.created_at, t.assigned_to
                FROM tickets t
                JOIN accounts a ON t.account_id = a.account_id
                WHERE LOWER(t.status) NOT IN ('closed', 'resolved')
                ORDER BY t.created_at ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT t.ticket_id, t.account_id, a.account_name, a.plan,
                       t.status, t.subject, t.description, t.created_at, t.assigned_to
                FROM tickets t
                JOIN accounts a ON t.account_id = a.account_id
                WHERE LOWER(t.status) NOT IN ('closed', 'resolved')
                  AND t.account_id = ?
                ORDER BY t.created_at ASC
                """,
                (session_account_id,),
            ).fetchall()

    from datetime import datetime

    SLA = config.SLA_MINUTES

    def infer_priority(subject: str) -> str:
        s = (subject or "").lower()
        p1_keywords = {"error", "500", "fail", "down", "outage", "exposed", "exposure", "security", "breach", "all "}
        p2_keywords = {"wrong", "incorrect", "not working", "issue", "delayed", "missing", "billing"}
        if any(k in s for k in p1_keywords):
            return "P1"
        if any(k in s for k in p2_keywords):
            return "P2"
        return "P3"

    try:
        snap_dt = datetime.strptime(snapshot.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        snap_dt = datetime.strptime(snapshot.strip()[:16], "%Y-%m-%d %H:%M")

    breached = []
    at_risk = []

    for r in rows:
        row = dict(r)
        plan = row.get("plan", "Standard")
        priority = infer_priority(row.get("subject", ""))
        sla_mins = SLA.get(plan, SLA["Standard"]).get(priority, 480)

        try:
            created_dt = datetime.strptime(row["created_at"].strip()[:16], "%Y-%m-%d %H:%M")
        except Exception:
            continue

        elapsed_mins = (snap_dt - created_dt).total_seconds() / 60
        remaining_mins = sla_mins - elapsed_mins

        entry = {
            **row,
            "inferred_priority": priority,
            "sla_target_minutes": sla_mins,
            "elapsed_minutes": round(elapsed_mins, 1),
            "sla_breached": elapsed_mins > sla_mins,
            "minutes_remaining": round(remaining_mins, 1),
        }

        if elapsed_mins > sla_mins:
            breached.append(entry)
        elif remaining_mins <= 30:
            at_risk.append(entry)

    return {
        "snapshot_time": snapshot,
        "sla_breached": breached,
        "sla_at_risk": at_risk,
        "breached_count": len(breached),
        "at_risk_count": len(at_risk),
    }


# ── Unified dispatch called by the orchestrator ────────────────────────────────

def lookup(
    operation: str,
    params: dict,
    session_account_id: str,
    is_internal: bool,
) -> dict:
    """
    Single entry point for the orchestrator.
    `operation` is one of the keys below; `params` carries operation-specific args.
    The session_account_id and is_internal flag come from the trusted session —
    never from the LLM's tool input.
    """
    ops = {
        "get_account_info": lambda p: get_account_info(
            p.get("account_id", session_account_id), session_account_id, is_internal
        ),
        "get_order": lambda p: get_order(p["order_id"], session_account_id, is_internal),
        "list_orders": lambda p: list_orders(session_account_id, p.get("status")),
        "get_ticket": lambda p: get_ticket(p["ticket_id"], session_account_id, is_internal),
        "list_tickets": lambda p: list_tickets(
            session_account_id,
            is_internal,
            p.get("target_account_id"),
            p.get("status"),
            p.get("subject"),
        ),
        "get_credit_balance": lambda p: get_credit_balance(session_account_id),
        "sla_breach_report": lambda p: sla_breach_report(session_account_id, is_internal),
        "proactive_report": lambda p: (
            issue_detector.run_full_report() if is_internal
            else {"error": "Proactive reports are only available to internal agents."}
        ),
    }

    handler = ops.get(operation)
    if handler is None:
        return {"error": f"Unknown operation: '{operation}'. Valid operations: {list(ops.keys())}"}

    try:
        return handler(params)
    except KeyError as e:
        return {"error": f"Missing required parameter: {e}"}
    except Exception as e:
        return {"error": f"Lookup failed: {e}"}
