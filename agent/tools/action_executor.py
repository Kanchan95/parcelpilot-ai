"""
Tool C — Action Executor (two-phase confirmation gate)

Phase 1: The LLM calls this tool → returns a confirmation request (does NOT execute).
Phase 2: The user explicitly confirms → confirm_action() is called → executes and logs.

The LLM is never told an action was completed until Phase 2 is done.
All executed actions are appended to the actions_log table.

Real schema notes:
  orders  : status values are UPPERCASE (BOOKED, PICKED_UP, DELIVERED, CANCELLED)
  tickets : no priority, resolved_at, or resolution columns;
            has historical_resolution, subject, description, channel, assigned_to
"""

import sqlite3
import uuid
import json
from datetime import datetime
from typing import Any

import config

_pending: dict[str, dict] = {}


def _log_action(
    action_id: str,
    account_id: str,
    session_id: str,
    action_type: str,
    parameters: dict,
    status: str,
    executed_by: str,
) -> None:
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO actions_log
            (action_id, account_id, session_id, action_type, parameters, status, executed_at, executed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id, account_id, session_id, action_type,
                json.dumps(parameters), status,
                datetime.utcnow().isoformat(), executed_by,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _update_order_status(order_id: str, account_id: str, new_status: str) -> None:
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE orders SET status = ? WHERE order_id = ? AND account_id = ?",
            (new_status.upper(), order_id, account_id),
        )
        conn.commit()
    finally:
        conn.close()


def _apply_credit_to_account(account_id: str, amount: float) -> None:
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE accounts SET credit_balance = credit_balance + ? WHERE account_id = ?",
            (amount, account_id),
        )
        conn.commit()
    finally:
        conn.close()


def _update_ticket_fields(ticket_id: str, account_id: str, updates: dict) -> None:
    """Update ticket columns. Only touches columns that exist in the real schema."""
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [ticket_id, account_id]
    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.execute(
            f"UPDATE tickets SET {cols} WHERE ticket_id = ? AND account_id = ?", vals
        )
        conn.commit()
    finally:
        conn.close()


# ── Phase 1: Request confirmation ─────────────────────────────────────────────

def request_action(
    action_type: str,
    parameters: dict,
    session_account_id: str,
    session_id: str,
    is_internal: bool,
) -> dict:
    """
    Called by the orchestrator when the LLM invokes execute_action.
    Does NOT perform the action — returns a confirmation payload that the UI
    surfaces to the user.
    """
    action_id = str(uuid.uuid4())

    summaries: dict[str, str] = {
        "cancel_order": (
            f"Cancel order {parameters.get('order_id')} "
            f"(fee waiver or standard fee will apply per policy and account agreement)."
        ),
        "apply_credit": (
            f"Apply a service credit of ₹{parameters.get('amount')} to account {session_account_id}. "
            f"Reason: {parameters.get('reason', 'not specified')}."
        ),
        "update_ticket_status": (
            f"Update ticket {parameters.get('ticket_id')} status to "
            f"'{parameters.get('new_status')}'."
        ),
        "escalate_ticket": (
            f"Escalate ticket {parameters.get('ticket_id')} — "
            f"priority: {parameters.get('priority', 'high')}. "
            f"Reason: {parameters.get('reason', 'not specified')}."
        ),
        "close_ticket": (
            f"Close ticket {parameters.get('ticket_id')} with resolution: "
            f"'{parameters.get('resolution', 'Resolved by AI support agent.')}'."
        ),
        "create_escalation": (
            f"Create a new escalation ticket for account {session_account_id}. "
            f"Reason: {parameters.get('reason', 'not specified')}. "
            f"Priority: {parameters.get('priority', 'high')}."
        ),
    }

    summary = summaries.get(action_type, f"Perform action: {action_type}.")

    _pending[action_id] = {
        "action_id": action_id,
        "action_type": action_type,
        "parameters": parameters,
        "session_account_id": session_account_id,
        "session_id": session_id,
        "is_internal": is_internal,
    }

    return {
        "status": "requires_confirmation",
        "action_id": action_id,
        "summary": summary,
        "action_type": action_type,
        "parameters": parameters,
        "warning": "This action has NOT been executed yet. Present this to the user and wait for confirmation.",
    }


# ── Phase 2: Execute after user confirmation ───────────────────────────────────

def confirm_action(action_id: str) -> dict:
    """Executes the pending action and removes it from the pending store."""
    pending = _pending.pop(action_id, None)
    if pending is None:
        return {"status": "error", "message": f"No pending action found with id {action_id}."}

    action_type = pending["action_type"]
    params = pending["parameters"]
    account_id = pending["session_account_id"]
    session_id = pending["session_id"]

    try:
        result = _execute(action_type, params, account_id)
        _log_action(action_id, account_id, session_id, action_type, params, "executed", account_id)
        return {"status": "executed", "action_type": action_type, "result": result}
    except Exception as e:
        _log_action(action_id, account_id, session_id, action_type, params, "failed", account_id)
        return {"status": "error", "message": str(e)}


def cancel_pending_action(action_id: str) -> dict:
    """Discards a pending action without executing it."""
    _pending.pop(action_id, None)
    return {"status": "cancelled", "message": "Action was cancelled. No changes were made."}


def get_pending_action(action_id: str) -> dict | None:
    return _pending.get(action_id)


# ── Internal execution dispatch ────────────────────────────────────────────────

def _execute(action_type: str, params: dict, account_id: str) -> dict:
    if action_type == "cancel_order":
        order_id = params["order_id"]
        _update_order_status(order_id, account_id, "CANCELLED")
        return {"message": f"Order {order_id} has been cancelled successfully."}

    if action_type == "apply_credit":
        amount = float(params["amount"])
        _apply_credit_to_account(account_id, amount)
        return {"message": f"₹{amount} service credit applied to account {account_id}."}

    if action_type == "update_ticket_status":
        ticket_id = params["ticket_id"]
        new_status = params["new_status"]
        _update_ticket_fields(ticket_id, account_id, {"status": new_status})
        return {"message": f"Ticket {ticket_id} status updated to '{new_status}'."}

    if action_type == "escalate_ticket":
        ticket_id = params["ticket_id"]
        reason = params.get("reason", "")
        # Real schema has no priority field; update status and append reason to description
        _update_ticket_fields(
            ticket_id, account_id, {"status": "escalated"}
        )
        if reason:
            # Append escalation note to description
            conn = sqlite3.connect(config.DB_PATH)
            try:
                row = conn.execute(
                    "SELECT description FROM tickets WHERE ticket_id = ? AND account_id = ?",
                    (ticket_id, account_id),
                ).fetchone()
                if row:
                    current = row[0] or ""
                    updated = current + f"\n\n[ESCALATED]: {reason}"
                    conn.execute(
                        "UPDATE tickets SET description = ? WHERE ticket_id = ? AND account_id = ?",
                        (updated, ticket_id, account_id),
                    )
                    conn.commit()
            finally:
                conn.close()
        return {"message": f"Ticket {ticket_id} escalated. Reason: {reason or 'not specified'}"}

    if action_type == "close_ticket":
        ticket_id = params["ticket_id"]
        resolution = params.get("resolution", "Resolved by AI support agent.")
        # Real schema uses historical_resolution; update status to 'resolved'
        _update_ticket_fields(
            ticket_id, account_id,
            {"status": "resolved", "historical_resolution": resolution},
        )
        return {"message": f"Ticket {ticket_id} resolved. Resolution recorded."}

    if action_type == "create_escalation":
        ticket_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
        reason = params.get("reason", "Escalation requested via AI support.")
        priority_label = params.get("priority", "high")
        subject = f"[{priority_label.upper()} ESCALATION] {reason[:80]}"
        conn = sqlite3.connect(config.DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO tickets
                (ticket_id, account_id, created_at, status, subject, description,
                 channel, assigned_to, last_customer_message_at, historical_resolution)
                VALUES (?, ?, ?, 'escalated', ?, ?, 'ai_agent', 'Unassigned', ?, NULL)
                """,
                (
                    ticket_id, account_id,
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                    subject, reason,
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "message": f"Escalation ticket {ticket_id} created.",
            "ticket_id": ticket_id,
            "priority": priority_label,
        }

    raise ValueError(f"Unknown action_type: '{action_type}'")
