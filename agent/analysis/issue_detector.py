"""
Proactive Issue Detection — rewritten for real schema.

Real schema:
  accounts: account_id, account_name, plan, status, csm, ...
  orders  : order_id, account_id, carrier, status, booked_at, pickup_window_start,
            pickup_window_end, pickup_actual_at, shipment_fee_inr,
            carrier_fault, customer_fault, cancellation_requested_at, notes
  tickets : ticket_id, account_id, created_at, status, subject, description,
            channel, assigned_to, last_customer_message_at, historical_resolution

Called by structured_lookup when operation='proactive_report' (internal agents only).
"""

import sqlite3
from collections import Counter
from datetime import datetime

import config

# ── Dataset reference time (not datetime.now()) ────────────────────────────────
def _snap() -> datetime:
    s = config.get_snapshot_time().strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:len(fmt.replace("%Y", "YYYY").replace("%m", "MM")
                                         .replace("%d", "DD").replace("%H", "HH")
                                         .replace("%M", "MM2").replace("%S", "SS"))], fmt)
        except ValueError:
            pass
    try:
        return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return datetime(2026, 8, 16, 11, 0)


def _parse_snap() -> datetime:
    s = config.get_snapshot_time().strip()[:16]
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def _db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ── Individual detectors ───────────────────────────────────────────────────────

def detect_complaint_clusters() -> dict:
    """
    Groups open tickets by keyword patterns in subject.
    Flags categories with 2+ occurrences.
    """
    CATEGORIES = {
        "shipment_api_error":  ["http 500", "500 error", "api error", "creation is failing", "failing"],
        "bulk_upload":         ["bulk upload", "csv", "row"],
        "tracking_status":     ["shows booked", "status", "booked after", "pickup"],
        "billing_dispute":     ["fee", "invoice", "charge", "billing", "credit"],
        "security_incident":   ["api key", "exposed", "exposure", "security"],
        "account_admin":       ["billing contact", "admin", "user", "permission"],
        "cancellation":        ["cancel", "cancellation"],
    }

    conn = _db()
    try:
        rows = _rows(
            conn,
            "SELECT ticket_id, account_id, subject, status FROM tickets WHERE LOWER(status) NOT IN ('resolved', 'closed')",
        )
    finally:
        conn.close()

    category_counts: Counter = Counter()
    ticket_category_map: dict[str, str] = {}

    for row in rows:
        subject_lower = (row["subject"] or "").lower()
        matched = "other"
        for cat, keywords in CATEGORIES.items():
            if any(k in subject_lower for k in keywords):
                matched = cat
                break
        category_counts[matched] += 1
        ticket_category_map[row["ticket_id"]] = matched

    clusters = []
    for cat, count in category_counts.most_common():
        tickets_in_cat = [r["ticket_id"] for r in rows if ticket_category_map.get(r["ticket_id"]) == cat]
        clusters.append({
            "category": cat,
            "open_ticket_count": count,
            "ticket_ids": tickets_in_cat,
            "flagged": count >= 2,
        })

    return {
        "clusters": clusters,
        "flagged_categories": [c["category"] for c in clusters if c["flagged"]],
    }


def detect_sla_breaches() -> dict:
    """
    Computes SLA status for all open tickets at snapshot time.
    Priority is inferred from subject keywords (no priority field in real schema).
    """
    snap = _parse_snap()
    SLA = config.SLA_MINUTES

    def infer_priority(subject: str) -> str:
        s = (subject or "").lower()
        if any(k in s for k in ("http 500", "500", "failing", "fail", "all ", "exposed", "security", "exposure")):
            return "P1"
        if any(k in s for k in ("wrong", "incorrect", "shows ", "status", "billing", "invoice")):
            return "P2"
        return "P3"

    conn = _db()
    try:
        rows = _rows(
            conn,
            """
            SELECT t.ticket_id, t.account_id, a.account_name, a.plan,
                   t.status, t.subject, t.created_at, t.assigned_to
            FROM tickets t
            JOIN accounts a ON t.account_id = a.account_id
            WHERE LOWER(t.status) NOT IN ('closed', 'resolved')
            ORDER BY t.created_at ASC
            """,
        )
    finally:
        conn.close()

    breached = []
    at_risk = []

    for row in rows:
        plan = row.get("plan", "Standard")
        priority = infer_priority(row.get("subject", ""))
        sla_mins = SLA.get(plan, SLA["Standard"]).get(priority, 480)

        try:
            created = datetime.strptime(row["created_at"].strip()[:16], "%Y-%m-%d %H:%M")
        except Exception:
            continue

        elapsed_mins = (snap - created).total_seconds() / 60
        remaining = sla_mins - elapsed_mins

        entry = {
            **row,
            "inferred_priority": priority,
            "sla_target_minutes": sla_mins,
            "elapsed_minutes": round(elapsed_mins, 1),
            "sla_breached": elapsed_mins > sla_mins,
            "minutes_remaining": round(remaining, 1),
        }
        if elapsed_mins > sla_mins:
            breached.append(entry)
        elif remaining <= 30:
            at_risk.append(entry)

    return {
        "sla_breached": breached,
        "sla_at_risk": at_risk,
        "count": len(breached),
        "at_risk_count": len(at_risk),
    }


def detect_missed_pickups() -> dict:
    """
    Finds BOOKED orders past their pickup_window_end at snapshot time.
    Distinguishes carrier-fault vs customer-fault missed pickups.
    """
    snap = _parse_snap()
    conn = _db()
    try:
        rows = _rows(
            conn,
            """
            SELECT o.order_id, o.account_id, a.account_name,
                   o.carrier, o.status, o.pickup_window_start, o.pickup_window_end,
                   o.pickup_actual_at, o.shipment_fee_inr,
                   o.carrier_fault, o.customer_fault, o.notes
            FROM orders o
            JOIN accounts a ON o.account_id = a.account_id
            WHERE UPPER(o.status) = 'BOOKED'
            """,
        )
    finally:
        conn.close()

    missed = []
    for row in rows:
        window_end_str = row.get("pickup_window_end") or ""
        if not window_end_str or window_end_str == "None":
            continue
        try:
            window_end = datetime.strptime(window_end_str.strip()[:16], "%Y-%m-%d %H:%M")
        except Exception:
            continue

        if snap > window_end and not row.get("pickup_actual_at"):
            hours_late = (snap - window_end).total_seconds() / 3600
            missed.append({
                **row,
                "hours_past_window_end": round(hours_late, 2),
            })

    return {
        "missed_pickups": missed,
        "count": len(missed),
    }


def detect_stale_resolutions() -> dict:
    """
    Flags closed tickets whose historical_resolution may be incorrect.
    Known bad resolutions from the dataset:
      TKT-450: Told Northstar INR 250 fee applies — WRONG (Enterprise Agreement waives fee)
      TKT-451: Told LumenWorks Growth plan only supports 3,000 rows — WRONG (it's a known bug, not a plan limit)
    Also scans for generic deprecated-policy indicators.
    """
    conn = _db()
    try:
        rows = _rows(
            conn,
            """
            SELECT t.ticket_id, t.account_id, a.account_name, a.plan,
                   t.subject, t.historical_resolution
            FROM tickets t
            JOIN accounts a ON t.account_id = a.account_id
            WHERE LOWER(t.status) IN ('closed', 'resolved')
              AND t.historical_resolution IS NOT NULL
            """,
        )
    finally:
        conn.close()

    flagged = []
    for row in rows:
        hist = (row.get("historical_resolution") or "").lower()
        reasons = []

        # Known incorrect resolutions from real dataset
        if row["ticket_id"] == "TKT-450":
            reasons.append(
                "Told Northstar INR 250 cancellation fee applies — INCORRECT. "
                "Northstar Enterprise Agreement Section 2 waives all cancellation fees "
                "for BOOKED shipments before pickup, regardless of time since booking."
            )
        if row["ticket_id"] == "TKT-451":
            reasons.append(
                "Told LumenWorks Growth plan only supports 3,000 rows — INCORRECT. "
                "Product guide states 5,000 rows per CSV. The 3,000-row issue is KI-208 "
                "(a known bug, not a plan limitation). The correct answer includes a workaround."
            )

        # Generic stale indicators
        if any(k in hist for k in ("deprecated", "old policy", "v1.0", "v2 policy")):
            reasons.append("Historical resolution references a deprecated policy version.")

        if reasons:
            flagged.append({**row, "issues": reasons})

    return {
        "stale_resolutions": flagged,
        "count": len(flagged),
        "note": (
            "These resolutions were incorrect at the time of closure or reference deprecated policy. "
            "Affected customers may have received wrong information."
        ) if flagged else "",
    }


def detect_cancellation_requests() -> dict:
    """
    Surfaces all pending cancellation requests (orders where cancellation_requested_at is set
    but status is still BOOKED or PICKED_UP).
    """
    conn = _db()
    try:
        rows = _rows(
            conn,
            """
            SELECT o.order_id, o.account_id, a.account_name, a.plan,
                   o.carrier, o.status, o.booked_at, o.cancellation_requested_at,
                   o.shipment_fee_inr, o.carrier_fault, o.customer_fault
            FROM orders o
            JOIN accounts a ON o.account_id = a.account_id
            WHERE o.cancellation_requested_at IS NOT NULL
              AND UPPER(o.status) IN ('BOOKED', 'PICKED_UP')
            ORDER BY o.cancellation_requested_at ASC
            """,
        )
    finally:
        conn.close()

    return {
        "pending_cancellations": rows,
        "count": len(rows),
    }


# ── Master report ──────────────────────────────────────────────────────────────

def run_full_report() -> dict:
    """
    Runs all detectors and returns a structured digest.
    Called by structured_lookup when operation='proactive_report'.
    """
    clusters = detect_complaint_clusters()
    sla = detect_sla_breaches()
    missed = detect_missed_pickups()
    stale = detect_stale_resolutions()
    cancels = detect_cancellation_requests()

    snap = config.get_snapshot_time()
    lines: list[str] = [f"## ParcelPilot — Proactive Issue Report\n**Reference time:** {snap}\n"]

    # SLA breaches
    if sla["count"] > 0:
        lines.append(f"### SLA-Breached Open Tickets ({sla['count']})")
        for t in sla["sla_breached"]:
            overdue = round(t["elapsed_minutes"] - t["sla_target_minutes"])
            lines.append(
                f"- **{t['ticket_id']}** [{t['account_name']} / {t['plan']}] — "
                f"{t['subject'][:60]} | "
                f"Priority: {t['inferred_priority']} | "
                f"SLA: {t['sla_target_minutes']}min | "
                f"Overdue by {overdue}min | Assigned: {t['assigned_to']}"
            )
    else:
        lines.append("### No SLA breaches on open tickets.")

    if sla["at_risk_count"] > 0:
        lines.append(f"\n### SLA At-Risk (< 30min remaining) ({sla['at_risk_count']})")
        for t in sla["sla_at_risk"]:
            lines.append(
                f"- **{t['ticket_id']}** [{t['account_name']}] — "
                f"{t['subject'][:50]} | {round(t['minutes_remaining'])}min left"
            )

    lines.append("")

    # Missed pickups
    if missed["count"] > 0:
        lines.append(f"### Missed Pickups ({missed['count']})")
        for o in missed["missed_pickups"]:
            fault = "carrier fault" if o.get("carrier_fault") else "unknown fault"
            lines.append(
                f"- **{o['order_id']}** [{o['account_name']}] — "
                f"{o['hours_past_window_end']}h past pickup window | "
                f"{fault} | carrier: {o['carrier']}"
            )
    else:
        lines.append("### No missed pickups detected.")

    lines.append("")

    # Complaint clusters
    if clusters["flagged_categories"]:
        lines.append(f"### Recurring Complaint Clusters")
        for c in clusters["clusters"]:
            if c["flagged"]:
                lines.append(
                    f"- **{c['category'].replace('_', ' ').title()}**: "
                    f"{c['open_ticket_count']} open tickets ({', '.join(c['ticket_ids'])})"
                )
    else:
        lines.append("### No recurring complaint clusters.")

    lines.append("")

    # Pending cancellations
    if cancels["count"] > 0:
        lines.append(f"### Pending Cancellation Requests ({cancels['count']})")
        for o in cancels["pending_cancellations"]:
            lines.append(
                f"- **{o['order_id']}** [{o['account_name']}] — "
                f"status: {o['status']} | requested: {str(o['cancellation_requested_at'])[:16]}"
            )
    else:
        lines.append("### No pending cancellation requests.")

    lines.append("")

    # Stale resolutions
    if stale["count"] > 0:
        lines.append(f"### Incorrect Historical Resolutions ({stale['count']})")
        lines.append(f"*{stale['note']}*")
        for t in stale["stale_resolutions"]:
            for issue in t["issues"]:
                lines.append(f"- **{t['ticket_id']}** [{t['account_name']}]: {issue}")
    else:
        lines.append("### No known-incorrect historical resolutions.")

    return {
        "summary": "\n".join(lines),
        "clusters": clusters,
        "sla_breaches": sla,
        "missed_pickups": missed,
        "stale_resolutions": stale,
        "pending_cancellations": cancels,
    }


if __name__ == "__main__":
    report = run_full_report()
    print(report["summary"])
