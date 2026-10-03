"""
Regression tests covering the primary demo scenarios.

These tests are deterministic and offline — they verify tool-layer behavior
against the real data without calling the Groq API.

Run: pytest tests/test_scenarios.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import structured_lookup


@pytest.fixture(autouse=True)
def _skip_if_no_chroma(request):
    """Skip tests marked @pytest.mark.chroma when ChromaDB has not been built."""
    if request.node.get_closest_marker("chroma") is not None:
        import config
        if not config.CHROMA_DIR.exists():
            pytest.skip("ChromaDB not initialised — run python -m ingestion.document_ingester")


# ── A. Primary Northstar demo: ORD-1001 cancellation ─────────────────────────

class TestNorthstarCancellationScenario:
    """
    Scenario: 'Can Northstar cancel ORD-1001 without a cancellation fee?'

    Correct answer: YES.
    Northstar Enterprise Agreement waives all fees for any BOOKED shipment
    before actual pickup, regardless of time elapsed since booking.
    """

    def test_ord1001_belongs_to_northstar(self):
        """ORD-1001 must be retrievable by ACCT-001 and belong to Northstar."""
        result = structured_lookup.get_order("ORD-1001", "ACCT-001", is_internal=False)
        assert "error" not in result, f"ORD-1001 should be accessible to ACCT-001: {result}"
        assert result["account_id"] == "ACCT-001"

    def test_ord1001_is_booked_not_yet_picked_up(self):
        """ORD-1001 must be BOOKED with no actual pickup — making it eligible for cancellation."""
        result = structured_lookup.get_order("ORD-1001", "ACCT-001", is_internal=False)
        assert result["status"] == "BOOKED", (
            f"ORD-1001 status is {result['status']!r} — should be BOOKED for the demo to work"
        )
        assert result.get("pickup_actual_at") is None, (
            "ORD-1001 shows an actual pickup time — cannot be cancelled after pickup"
        )

    @pytest.mark.chroma
    def test_northstar_agreement_retrieved_for_acct001(self):
        """ACCT-001 query must retrieve the Northstar Enterprise Agreement."""
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        source_types = [r["source_type"] for r in result["results"]]
        assert "customer_agreement" in source_types, (
            "Northstar Enterprise Agreement (customer_agreement) must appear in ACCT-001 search results"
        )

    @pytest.mark.chroma
    def test_northstar_agreement_outranks_sop(self):
        """
        Northstar agreement (weight 3.0×) must rank above the general SOP (weight 1.8×).
        Re-ranking formula: weighted_score = cosine_similarity × authority_weight.
        """
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        sources = result["results"]
        assert sources[0]["source_type"] == "customer_agreement", (
            f"Top result should be customer_agreement, got {sources[0]['source_type']!r}"
        )

    @pytest.mark.chroma
    def test_agreement_override_conflict_detected(self):
        """
        When the Northstar agreement and general cancellation SOP are both retrieved,
        an agreement_override conflict must be emitted.
        """
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        conflict_types = [c["type"] for c in result["conflicts"]]
        assert "agreement_override" in conflict_types, (
            f"Expected agreement_override conflict; got conflicts: {result['conflicts']}"
        )

    @pytest.mark.chroma
    def test_lumenworks_agreement_not_visible_to_northstar(self):
        """ACCT-001 must not receive ACCT-002's (LumenWorks) service agreement."""
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        for r in result["results"]:
            assert "LumenWorks" not in r["source"], (
                f"Cross-account document leak: ACCT-001 retrieved LumenWorks agreement"
            )


# ── B. LumenWorks service-credit scenario: ORD-2002 ──────────────────────────

class TestLumenWorksServiceCreditScenario:
    """
    Scenario: 'Is ORD-2002 eligible for a service credit?'

    Correct answer: YES, INR 300 fixed credit.
    LumenWorks agreement: >4h past window end, carrier fault → INR 300.
    Snapshot time is 2026-08-16 11:00. Pickup window ended at 06:30 → 4.5h late.
    """

    def test_ord2002_belongs_to_lumenworks(self):
        result = structured_lookup.get_order("ORD-2002", "ACCT-002", is_internal=False)
        assert "error" not in result
        assert result["account_id"] == "ACCT-002"

    def test_ord2002_has_carrier_fault(self):
        """carrier_fault must be set for the credit to be eligible."""
        result = structured_lookup.get_order("ORD-2002", "ACCT-002", is_internal=False)
        assert result.get("carrier_fault") in (1, True), (
            f"ORD-2002 carrier_fault={result.get('carrier_fault')!r} — must be truthy for credit eligibility"
        )

    def test_ord2002_has_no_actual_pickup(self):
        """ORD-2002 must not have been picked up at snapshot time."""
        result = structured_lookup.get_order("ORD-2002", "ACCT-002", is_internal=False)
        assert result.get("pickup_actual_at") is None, (
            "ORD-2002 shows a pickup — credit scenario requires missed pickup"
        )

    @pytest.mark.chroma
    def test_lumenworks_agreement_retrieved_for_acct002(self):
        from agent.tools.document_search import search
        result = search("service credit missed pickup", "ACCT-002")
        source_types = [r["source_type"] for r in result["results"]]
        assert "customer_agreement" in source_types

    @pytest.mark.chroma
    def test_northstar_agreement_not_visible_to_lumenworks(self):
        from agent.tools.document_search import search
        result = search("service credit missed pickup", "ACCT-002")
        for r in result["results"]:
            assert "Northstar" not in r["source"]


# ── C. Snapshot time ──────────────────────────────────────────────────────────

class TestSnapshotTime:
    """The snapshot time from the Excel data must be available at runtime."""

    def test_snapshot_time_is_not_default_fallback(self):
        import config
        snap = config.get_snapshot_time()
        assert snap != "2026-08-01 00:00:00", (
            "Snapshot time is the default fallback — run python -m ingestion.excel_ingester"
        )

    def test_snapshot_time_matches_excel(self):
        import config
        snap = config.get_snapshot_time()
        # The Excel README sheet specifies 2026-08-16 11:00
        assert "2026-08-16" in snap, f"Snapshot time {snap!r} does not match snapshot date 2026-08-16"
        assert "11:00" in snap, f"Snapshot time {snap!r} does not match snapshot time 11:00"

    def test_snapshot_file_exists(self):
        import config
        assert config.SNAPSHOT_TIME_FILE.exists(), (
            ".snapshot_time file missing — run python -m ingestion.excel_ingester"
        )


# ── D. Cross-account access control ──────────────────────────────────────────

class TestCrossAccountAccessControl:
    def test_acct001_cannot_read_ord2001(self):
        """Primary cross-account block demo: ACCT-001 asks for ACCT-002's order."""
        result = structured_lookup.get_order(
            order_id="ORD-2001",
            session_account_id="ACCT-001",
            is_internal=False,
        )
        assert "error" in result
        error_msg = result["error"].lower()
        assert "not found" in error_msg or "not accessible" in error_msg

    def test_proactive_report_blocked_for_customers(self):
        """Proactive report is internal-only — customer accounts must be denied."""
        result = structured_lookup.lookup("proactive_report", {}, "ACCT-001", False)
        assert "error" in result
        assert "internal" in result["error"].lower()


# ── E. Proactive issue detection ──────────────────────────────────────────────

class TestProactiveIssueDetection:
    def test_proactive_report_has_expected_structure(self):
        result = structured_lookup.lookup("proactive_report", {}, "INTERNAL", True)
        assert "error" not in result
        for key in ("summary", "sla_breaches", "missed_pickups", "stale_resolutions", "pending_cancellations"):
            assert key in result, f"Missing key {key!r} from proactive report"

    def test_proactive_report_detects_stale_resolutions(self):
        """TKT-450 and/or TKT-451 must appear as stale resolutions in the data."""
        result = structured_lookup.lookup("proactive_report", {}, "INTERNAL", True)
        # stale_resolutions is a dict with a nested list keyed "stale_resolutions"
        stale_data = result["stale_resolutions"]
        stale_list = stale_data.get("stale_resolutions", stale_data) if isinstance(stale_data, dict) else stale_data
        stale_ids = {r.get("ticket_id") for r in stale_list if isinstance(r, dict)}
        assert stale_ids & {"TKT-450", "TKT-451"}, (
            f"Expected TKT-450 or TKT-451 in stale resolutions; got {stale_ids}"
        )

    def test_proactive_report_detects_missed_pickups(self):
        """ORD-2002 has a missed pickup window at snapshot time."""
        result = structured_lookup.lookup("proactive_report", {}, "INTERNAL", True)
        assert len(result["missed_pickups"]) >= 1, (
            "Expected at least one missed pickup in the data"
        )

    def test_proactive_report_summary_is_non_empty(self):
        result = structured_lookup.lookup("proactive_report", {}, "INTERNAL", True)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 100, "Proactive report summary seems too short"


# ── F. Conflict detection ─────────────────────────────────────────────────────

class TestConflictDetection:
    """Verify conflict metadata structure for the source documents."""

    @pytest.mark.chroma
    def test_agreement_override_conflict_has_required_fields(self):
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        overrides = [c for c in result["conflicts"] if c["type"] == "agreement_override"]
        assert overrides, "No agreement_override conflict detected for ACCT-001 cancellation query"
        c = overrides[0]
        assert "trusted_source" in c
        assert "overridden_source" in c
        assert "Northstar" in c["trusted_source"]

    @pytest.mark.chroma
    def test_version_conflict_has_required_fields(self):
        from agent.tools.document_search import search
        result = search("cancellation fee", "ACCT-001")
        version_conflicts = [c for c in result["conflicts"] if c["type"] == "version_conflict"]
        assert version_conflicts, "No version_conflict detected (current vs deprecated policy)"
        c = version_conflicts[0]
        assert "trusted_source" in c
        assert "deprecated_source" in c

    @pytest.mark.chroma
    def test_product_guide_has_correct_authority_weight(self):
        """product_guide must use weight 1.6× (not the default 1.0× fallback)."""
        import config
        assert "product_guide" in config.AUTHORITY_WEIGHTS, (
            "product_guide missing from config.AUTHORITY_WEIGHTS — falls back to 1.0"
        )
        assert config.AUTHORITY_WEIGHTS["product_guide"] == 1.6
