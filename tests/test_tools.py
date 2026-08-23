"""
Unit/integration tests for the three agent tools.

Setup (one-time):
  python -m ingestion.excel_ingester
  python -m ingestion.document_ingester

Run: pytest tests/test_tools.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import action_executor, structured_lookup


# ── Tool B: Structured Lookup ──────────────────────────────────────────────────

class TestStructuredLookup:
    def test_get_account_info_returns_company(self):
        result = structured_lookup.get_account_info("ACCT-001", "ACCT-001", is_internal=False)
        assert result.get("account_name") == "Northstar Logistics"
        assert result.get("plan") == "Enterprise"

    def test_get_order_returns_amount(self):
        result = structured_lookup.get_order("ORD-1001", "ACCT-001", is_internal=False)
        assert result.get("shipment_fee_inr") == 4200

    def test_list_orders_returns_multiple(self):
        result = structured_lookup.list_orders("ACCT-001")
        assert result["count"] >= 2

    def test_list_orders_status_filter(self):
        # ORD-1001 and ORD-1002 are BOOKED and PICKED_UP respectively — filter for BOOKED
        result = structured_lookup.list_orders("ACCT-001", status_filter="BOOKED")
        for order in result["orders"]:
            assert order["status"] == "BOOKED"
        assert result["count"] >= 1

    def test_get_ticket_returns_correct_fields(self):
        result = structured_lookup.get_ticket("TKT-504", "ACCT-001", is_internal=False)
        assert "error" not in result
        assert result.get("ticket_id") == "TKT-504"
        assert result.get("account_id") == "ACCT-001"

    def test_sla_breach_report_has_correct_structure(self):
        report = structured_lookup.sla_breach_report("ACCT-001", is_internal=False)
        assert "sla_breached" in report
        assert "sla_at_risk" in report
        assert isinstance(report["sla_breached"], list)
        # All breached tickets must belong to the requesting account
        for ticket in report["sla_breached"]:
            assert ticket["account_id"] == "ACCT-001"

    def test_unknown_operation_returns_error(self):
        result = structured_lookup.lookup("nonexistent_op", {}, "ACCT-001", False)
        assert "error" in result

    def test_get_order_missing_param_returns_error(self):
        result = structured_lookup.lookup("get_order", {}, "ACCT-001", False)
        assert "error" in result


# ── Tool C: Action Executor ────────────────────────────────────────────────────

class TestActionExecutor:
    def test_request_action_returns_requires_confirmation(self):
        result = action_executor.request_action(
            action_type="update_ticket_status",
            parameters={"ticket_id": "TKT-504", "new_status": "in_progress"},
            session_account_id="ACCT-001",
            session_id="test",
            is_internal=False,
        )
        assert result["status"] == "requires_confirmation"
        assert "action_id" in result
        assert "summary" in result
        # Clean up to avoid polluting other tests
        action_executor.cancel_pending_action(result["action_id"])

    def test_action_not_executed_before_confirmation(self):
        result = action_executor.request_action(
            action_type="update_ticket_status",
            parameters={"ticket_id": "TKT-501", "new_status": "in_progress"},
            session_account_id="ACCT-001",
            session_id="test",
            is_internal=False,
        )
        action_id = result["action_id"]
        # Ticket status must NOT be changed yet (gate not passed)
        ticket = structured_lookup.get_ticket("TKT-501", "ACCT-001", is_internal=False)
        assert ticket.get("status") != "in_progress", (
            "Action executed before user confirmation — confirmation gate is broken!"
        )
        action_executor.cancel_pending_action(action_id)

    def test_cancel_pending_action_discards_it(self):
        result = action_executor.request_action(
            action_type="apply_credit",
            parameters={"amount": 100, "reason": "test"},
            session_account_id="ACCT-001",
            session_id="test",
            is_internal=False,
        )
        action_id = result["action_id"]
        cancel_result = action_executor.cancel_pending_action(action_id)
        assert cancel_result["status"] == "cancelled"
        # Confirming a cancelled action must fail
        confirm_result = action_executor.confirm_action(action_id)
        assert confirm_result["status"] == "error"

    def test_confirm_nonexistent_action_returns_error(self):
        result = action_executor.confirm_action("does-not-exist-uuid")
        assert result["status"] == "error"

    def test_escalate_ticket_updates_status(self):
        result = action_executor.request_action(
            action_type="escalate_ticket",
            parameters={"ticket_id": "TKT-504", "reason": "Critical issue requires immediate attention"},
            session_account_id="ACCT-001",
            session_id="test",
            is_internal=False,
        )
        action_id = result["action_id"]
        executed = action_executor.confirm_action(action_id)
        assert executed["status"] == "executed"
        ticket = structured_lookup.get_ticket("TKT-504", "ACCT-001", is_internal=False)
        assert ticket.get("status") == "escalated"


# ── Trust Hierarchy (via document_search) ─────────────────────────────────────

class TestDocumentSearch:
    """
    Requires ChromaDB to be populated.
    Run: python -m ingestion.document_ingester
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_chroma(self):
        import config
        if not config.CHROMA_DIR.exists():
            pytest.skip("ChromaDB not initialised — run python -m ingestion.document_ingester")

    def test_search_returns_results(self):
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        assert result["total_results"] > 0

    def test_northstar_agreement_ranks_above_policy(self):
        """Northstar agreement (weight 3.0×) must rank above SOP (weight 1.8×)."""
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        sources = [r["source_type"] for r in result["results"]]
        assert "customer_agreement" in sources, "Northstar agreement must be retrieved for ACCT-001"
        agreement_idx = next(i for i, s in enumerate(sources) if s == "customer_agreement")
        # All policy/SOP docs must rank below the agreement
        for i, s in enumerate(sources):
            if s in ("current_policy", "current_sop"):
                assert agreement_idx < i, (
                    f"customer_agreement (idx {agreement_idx}) must rank above {s} (idx {i})"
                )

    def test_lumenworks_cannot_see_northstar_agreement(self):
        """ACCT-002 (LumenWorks) must not retrieve ACCT-001 (Northstar) agreement."""
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-002")
        for r in result["results"]:
            assert "Northstar" not in r["source"], (
                f"Cross-account document leak: LumenWorks retrieved Northstar's agreement"
            )

    def test_deprecated_chunks_have_low_authority(self):
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-002")
        for r in result["results"]:
            if r["is_deprecated"]:
                assert r["authority_level"] < 50, (
                    f"Deprecated doc {r['source']} has unexpectedly high authority {r['authority_level']}"
                )

    def test_conflict_structure_is_valid(self):
        from agent.tools.document_search import search
        result = search("cancellation policy", "ACCT-001")
        assert isinstance(result["conflicts"], list)
        for c in result["conflicts"]:
            assert "type" in c
            assert "message" in c
