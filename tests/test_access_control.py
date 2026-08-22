"""
Integration tests for access control.

These tests hit the real SQLite DB (must run setup first):
  python scripts/generate_mock_data.py
  python -m ingestion.excel_ingester

Run: pytest tests/test_access_control.py -v
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import structured_lookup, action_executor


class TestCrossAccountBlocking:
    """A customer must never see another account's data."""

    def test_get_order_blocked_for_wrong_account(self):
        # ORD-2001 belongs to ACC-002; ACC-001 customer should not see it
        result = structured_lookup.get_order(
            order_id="ORD-2001",
            session_account_id="ACC-001",
            is_internal=False,
        )
        assert "error" in result
        assert "not found or not accessible" in result["error"].lower()

    def test_get_order_allowed_for_owner(self):
        # ORD-1001 belongs to ACCT-001; ACCT-001 customer should see it
        result = structured_lookup.get_order(
            order_id="ORD-1001",
            session_account_id="ACCT-001",
            is_internal=False,
        )
        assert "error" not in result
        assert result["order_id"] == "ORD-1001"
        assert result["account_id"] == "ACCT-001"

    def test_list_orders_only_returns_own_account(self):
        result = structured_lookup.list_orders(session_account_id="ACCT-001")
        orders = result["orders"]
        assert len(orders) > 0
        for order in orders:
            assert order["account_id"] == "ACCT-001", (
                f"Cross-account leak: {order['order_id']} belongs to {order['account_id']}"
            )

    def test_get_ticket_blocked_for_wrong_account(self):
        # TKT-005 belongs to ACC-002
        result = structured_lookup.get_ticket(
            ticket_id="TKT-005",
            session_account_id="ACC-001",
            is_internal=False,
        )
        assert "error" in result

    def test_list_tickets_scoped_to_account(self):
        result = structured_lookup.list_tickets(
            session_account_id="ACC-002",
            is_internal=False,
        )
        for ticket in result["tickets"]:
            assert ticket["account_id"] == "ACC-002"

    def test_internal_agent_can_access_any_order(self):
        # Internal agents bypass account scoping
        result = structured_lookup.get_order(
            order_id="ORD-2001",
            session_account_id="INTERNAL",
            is_internal=True,
        )
        assert "error" not in result
        assert result["order_id"] == "ORD-2001"

    def test_internal_agent_can_list_all_tickets(self):
        result = structured_lookup.list_tickets(
            session_account_id="INTERNAL",
            is_internal=True,
            target_account_id=None,  # all accounts
        )
        account_ids = {t["account_id"] for t in result["tickets"]}
        assert len(account_ids) > 1, "Internal agent should see tickets from multiple accounts"


class TestActionAccessControl:
    """Actions must be scoped to the session account."""

    def test_cancel_order_does_not_affect_other_account(self):
        # Request cancel on ORD-2002 (ACC-002) while logged in as ACC-001
        pending = action_executor.request_action(
            action_type="cancel_order",
            parameters={"order_id": "ORD-2002"},
            session_account_id="ACC-001",
            session_id="test-session",
            is_internal=False,
        )
        assert pending["status"] == "requires_confirmation"
        action_id = pending["action_id"]

        result = action_executor.confirm_action(action_id)
        # The action executor targets session_account_id (ACC-001), so the UPDATE
        # WHERE account_id='ACC-001' AND order_id='ORD-2002' will match 0 rows.
        # ORD-2002 remains untouched.
        assert result["status"] == "executed"
        # Verify ORD-2002 still exists under ACC-002 with unchanged status
        order = structured_lookup.get_order("ORD-2002", "ACC-002", is_internal=True)
        assert order.get("status") != "cancelled", (
            "Cross-account action leaked: ORD-2002 (ACC-002) was cancelled by ACC-001 session"
        )


class TestCreditBalance:
    def test_credit_balance_visible_to_own_account(self):
        result = structured_lookup.get_credit_balance("ACCT-001")
        assert "error" not in result
        assert result["account_id"] == "ACCT-001"
        assert "credit_balance" in result

    def test_sla_breach_report_scoped_to_customer(self):
        result = structured_lookup.sla_breach_report("ACCT-001", is_internal=False)
        for ticket in result["sla_breached"]:
            assert ticket["account_id"] == "ACCT-001"
