"""
Generates the parcelpilot_data.xlsx file with realistic accounts, orders, and tickets.
Run once: python scripts/generate_mock_data.py
"""

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import random

random.seed(42)
BASE_DATE = datetime(2026, 8, 1)
OUT_PATH = Path(__file__).parent.parent / "data" / "structured" / "parcelpilot_data.xlsx"


def d(days: int) -> datetime:
    return BASE_DATE - timedelta(days=days)


def make_accounts() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "account_id": "ACC-001",
            "company_name": "Acme Corp",
            "plan": "enterprise",
            "contact_email": "ops@acmecorp.com",
            "contract_start": "2024-01-15",
            "contract_end": "2026-01-14",
            "monthly_volume": 2400,
            "credit_balance": 3500.00,
            "status": "active",
        },
        {
            "account_id": "ACC-002",
            "company_name": "Globex Ltd",
            "plan": "professional",
            "contact_email": "logistics@globex.com",
            "contract_start": "2024-04-01",
            "contract_end": "2025-03-31",
            "monthly_volume": 310,
            "credit_balance": 0.00,
            "status": "active",
        },
        {
            "account_id": "ACC-003",
            "company_name": "Initech Inc",
            "plan": "starter",
            "contact_email": "support@initech.in",
            "contract_start": "2025-06-01",
            "contract_end": "2026-05-31",
            "monthly_volume": 45,
            "credit_balance": 250.00,
            "status": "active",
        },
    ])


def make_orders() -> pd.DataFrame:
    rows = [
        # ACC-001 orders
        {
            "order_id": "ORD-1001",
            "account_id": "ACC-001",
            "status": "delivered",
            "tracking_number": "PP100120240801",
            "origin": "Mumbai",
            "destination": "Delhi",
            "weight_kg": 12.5,
            "amount": 4800.00,
            "service_type": "express",
            "created_at": d(10),
            "delivered_at": d(8),
            "estimated_delivery": d(8),
        },
        {
            "order_id": "ORD-1002",
            "account_id": "ACC-001",
            "status": "in_transit",
            "tracking_number": "PP100220240802",
            "origin": "Pune",
            "destination": "Chennai",
            "weight_kg": 3.2,
            "amount": 1650.00,
            "service_type": "standard",
            "created_at": d(2),
            "delivered_at": None,
            "estimated_delivery": d(-1),  # future
        },
        {
            "order_id": "ORD-1003",
            "account_id": "ACC-001",
            "status": "pending",
            "tracking_number": "PP100320240803",
            "origin": "Bangalore",
            "destination": "Hyderabad",
            "weight_kg": 8.0,
            "amount": 2200.00,
            "service_type": "standard",
            "created_at": d(0),  # today
            "delivered_at": None,
            "estimated_delivery": d(-3),
        },
        {
            "order_id": "ORD-1004",
            "account_id": "ACC-001",
            "status": "delivered",
            "tracking_number": "PP100420240804",
            "origin": "Mumbai",
            "destination": "Kolkata",
            "weight_kg": 22.0,
            "amount": 8900.00,
            "service_type": "overnight",
            "created_at": d(40),  # 40 days ago - still in Acme's 45-day refund window
            "delivered_at": d(38),
            "estimated_delivery": d(39),
        },
        {
            "order_id": "ORD-1005",
            "account_id": "ACC-001",
            "status": "cancelled",
            "tracking_number": None,
            "origin": "Delhi",
            "destination": "Jaipur",
            "weight_kg": 1.5,
            "amount": 600.00,
            "service_type": "standard",
            "created_at": d(5),
            "delivered_at": None,
            "estimated_delivery": d(2),
        },
        # ACC-002 orders
        {
            "order_id": "ORD-2001",
            "account_id": "ACC-002",
            "status": "delivered",
            "tracking_number": "PP200120240810",
            "origin": "Chennai",
            "destination": "Bangalore",
            "weight_kg": 5.0,
            "amount": 1200.00,
            "service_type": "standard",
            "created_at": d(15),
            "delivered_at": d(12),
            "estimated_delivery": d(13),
        },
        {
            "order_id": "ORD-2002",
            "account_id": "ACC-002",
            "status": "pending",
            "tracking_number": "PP200220240811",
            "origin": "Hyderabad",
            "destination": "Mumbai",
            "weight_kg": 7.5,
            "amount": 2800.00,
            "service_type": "express",
            "created_at": d(1),
            "delivered_at": None,
            "estimated_delivery": d(-2),
        },
        {
            "order_id": "ORD-2003",
            "account_id": "ACC-002",
            "status": "delivered",
            "tracking_number": "PP200320240812",
            "origin": "Pune",
            "destination": "Delhi",
            "weight_kg": 14.0,
            "amount": 5500.00,
            "service_type": "standard",
            "created_at": d(35),  # outside 30-day standard window; would fail standard policy
            "delivered_at": d(32),
            "estimated_delivery": d(33),
        },
        # ACC-003 orders
        {
            "order_id": "ORD-3001",
            "account_id": "ACC-003",
            "status": "in_transit",
            "tracking_number": "PP300120240820",
            "origin": "Kolkata",
            "destination": "Bhubaneswar",
            "weight_kg": 2.1,
            "amount": 480.00,
            "service_type": "standard",
            "created_at": d(3),
            "delivered_at": None,
            "estimated_delivery": d(-1),
        },
        {
            "order_id": "ORD-3002",
            "account_id": "ACC-003",
            "status": "delivered",
            "tracking_number": "PP300220240821",
            "origin": "Bangalore",
            "destination": "Mysore",
            "weight_kg": 0.8,
            "amount": 220.00,
            "service_type": "standard",
            "created_at": d(20),
            "delivered_at": d(19),
            "estimated_delivery": d(18),
        },
    ]
    return pd.DataFrame(rows)


def make_tickets() -> pd.DataFrame:
    rows = [
        # ACC-001 tickets
        {
            "ticket_id": "TKT-001",
            "account_id": "ACC-001",
            "order_id": "ORD-1004",
            "issue_type": "refund",
            "status": "open",
            "priority": "medium",
            "description": "Customer requesting refund for ORD-1004 delivered 38 days ago. Item arrived damaged.",
            "resolution": None,
            "created_at": d(2),
            "updated_at": d(2),
            "resolved_at": None,
            "sla_breach": False,  # Acme SLA: 4h first response, 2 days resolution
        },
        {
            "ticket_id": "TKT-002",
            "account_id": "ACC-001",
            "order_id": "ORD-1001",
            "issue_type": "billing",
            "status": "resolved",
            "priority": "low",
            "description": "Customer queried invoice discrepancy of ₹200.",
            "resolution": "Overcharge confirmed. ₹200 credit applied to account. Resolved per SOP-05.",
            "created_at": d(12),
            "updated_at": d(11),
            "resolved_at": d(11),
            "sla_breach": False,
        },
        {
            "ticket_id": "TKT-003",
            "account_id": "ACC-001",
            "order_id": None,
            "issue_type": "account",
            "status": "open",
            "priority": "high",
            "description": "Customer requesting API rate limit increase for upcoming product launch.",
            "resolution": None,
            "created_at": d(1),
            "updated_at": d(1),
            "resolved_at": None,
            "sla_breach": False,
        },
        {
            "ticket_id": "TKT-004",
            "account_id": "ACC-001",
            "order_id": "ORD-1002",
            "issue_type": "delivery",
            "status": "in_progress",
            "priority": "high",
            "description": "Order ORD-1002 is overdue by 2 days. Customer reports no tracking updates.",
            "resolution": None,
            "created_at": d(3),
            "updated_at": d(1),
            "resolved_at": None,
            "sla_breach": True,  # Acme SLA breached (>8 hours for critical, this is 2 days old)
        },
        # ACC-002 tickets
        {
            "ticket_id": "TKT-005",
            "account_id": "ACC-002",
            "order_id": "ORD-2001",
            "issue_type": "billing",
            "status": "open",
            "priority": "medium",
            "description": "Disputed charge of ₹350 on latest invoice. No corresponding order found.",
            "resolution": None,
            "created_at": d(4),
            "updated_at": d(4),
            "resolved_at": None,
            "sla_breach": True,  # standard 24h SLA for professional — 4 days open
        },
        {
            "ticket_id": "TKT-006",
            "account_id": "ACC-002",
            "order_id": "ORD-2003",
            "issue_type": "refund",
            "status": "open",
            "priority": "medium",
            "description": "Customer requesting refund for ORD-2003. Order delivered 32 days ago — outside standard 30-day window but customer claims they were told 14 days was the window.",
            "resolution": None,
            "created_at": d(3),
            "updated_at": d(3),
            "resolved_at": None,
            "sla_breach": False,
        },
        {
            "ticket_id": "TKT-007",
            "account_id": "ACC-002",
            "order_id": None,
            "issue_type": "billing",
            "status": "resolved",
            "priority": "low",
            "description": "Customer confused about monthly invoice structure.",
            "resolution": "Explained consolidated billing model. No action required.",
            "created_at": d(20),
            "updated_at": d(19),
            "resolved_at": d(19),
            "sla_breach": False,
        },
        # ACC-003 tickets
        {
            "ticket_id": "TKT-008",
            "account_id": "ACC-003",
            "order_id": "ORD-3001",
            "issue_type": "delivery",
            "status": "open",
            "priority": "medium",
            "description": "Order ORD-3001 is 1 day overdue. Customer asking for update.",
            "resolution": None,
            "created_at": d(1),
            "updated_at": d(1),
            "resolved_at": None,
            "sla_breach": False,
        },
        {
            "ticket_id": "TKT-009",
            "account_id": "ACC-003",
            "order_id": "ORD-3002",
            "issue_type": "billing",
            "status": "resolved",
            "priority": "low",
            "description": "Customer questioned the express surcharge on ORD-3002.",
            "resolution": "Explained non-refundable express surcharge policy (Policy v1.0 referenced in error — should have cited v2.0). Credit of ₹50 applied as goodwill.",
            "created_at": d(22),
            "updated_at": d(21),
            "resolved_at": d(21),
            "sla_breach": False,
        },
        # Proactive detection: recurring billing issues cluster
        {
            "ticket_id": "TKT-010",
            "account_id": "ACC-002",
            "order_id": None,
            "issue_type": "billing",
            "status": "resolved",
            "priority": "low",
            "description": "Unexpected charge on account.",
            "resolution": "Charge was valid. Explained to customer.",
            "created_at": d(30),
            "updated_at": d(29),
            "resolved_at": d(29),
            "sla_breach": False,
        },
        {
            "ticket_id": "TKT-011",
            "account_id": "ACC-001",
            "order_id": None,
            "issue_type": "billing",
            "status": "resolved",
            "priority": "low",
            "description": "Invoice amount mismatch.",
            "resolution": "System bug caused duplicate line item. ₹400 credit applied.",
            "created_at": d(28),
            "updated_at": d(27),
            "resolved_at": d(27),
            "sla_breach": False,
        },
        {
            "ticket_id": "TKT-012",
            "account_id": "ACC-003",
            "order_id": None,
            "issue_type": "billing",
            "status": "open",
            "priority": "low",
            "description": "Billing cycle confusion — charged twice in one month.",
            "resolution": None,
            "created_at": d(5),
            "updated_at": d(5),
            "resolved_at": None,
            "sla_breach": True,
        },
    ]
    return pd.DataFrame(rows)


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        make_accounts().to_excel(writer, sheet_name="Accounts", index=False)
        make_orders().to_excel(writer, sheet_name="Orders", index=False)
        make_tickets().to_excel(writer, sheet_name="Tickets", index=False)
    print(f"Mock data written to {OUT_PATH}")


if __name__ == "__main__":
    main()
