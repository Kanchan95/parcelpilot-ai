# Low-Level Design — ParcelPilot AI Support System

## 1. Module Dependency Graph

```
config.py  (no deps — read by everything)
     │
     ├─▶ ingestion/document_ingester.py  (chromadb, sentence-transformers, pdfplumber)
     ├─▶ ingestion/excel_ingester.py     (pandas, sqlite3)
     │
     ├─▶ agent/tools/document_search.py  (chromadb)
     ├─▶ agent/tools/structured_lookup.py (sqlite3)
     ├─▶ agent/tools/action_executor.py   (sqlite3)
     │
     ├─▶ agent/analysis/issue_detector.py (sqlite3)
     ├─▶ agent/orchestrator.py  (openai SDK → Groq endpoint, all three tools)
     │
     └─▶ server.py      (fastapi, uvicorn, orchestrator)
                         serves React SPA from web/dist/ + all /api/* routes
```

Active server: `server.py` (port 8080).
Frontend: `web/` (React + Vite, built to `web/dist/`).

---

## 2. Class / Module Interfaces

### 2.1 `agent/orchestrator.py`

```python
class Orchestrator:
    account_id: str          # from trusted session
    is_internal: bool
    session_id: str
    client: openai.OpenAI    # pointed at Groq endpoint
    model: str               # e.g. "openai/gpt-oss-120b"
    messages: list[dict]     # full message history (OpenAI format)

    def chat(user_message: str) -> AgentResponse
    def notify_confirmation(action_id: str, confirmed: bool) -> AgentResponse

@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall]
    pending_action: dict | None   # set when action_executor returns "requires_confirmation"

@dataclass
class ToolCall:
    name: str
    tool_use_id: str
    inputs: dict
    output: dict
```

**ReAct loop logic (OpenAI format):**
```
while iterations < MAX_ITERATIONS:
    response = client.chat.completions.create(tools=tool_defs, messages=history)
    if finish_reason == "stop":   → extract text, return
    if finish_reason == "tool_calls":
        for each tool_call:
            result = dispatch_tool(name, inputs)
            if result.status == "requires_confirmation":
                store pending_action
                (LLM gets the confirmation summary and writes its response)
        append tool_results to history
        continue
```

---

### 2.2 `agent/tools/document_search.py`

```python
def search(query: str, account_id: str) -> dict:
    """
    Returns:
    {
      "results": [
        {
          "source": "Northstar Logistics Enterprise Agreement",
          "source_type": "customer_agreement",
          "is_deprecated": false,
          "authority_level": 100,
          "content": "...",
          "relevance_score": 0.847
        }, ...
      ],
      "conflicts": [
        {
          "type": "agreement_override",
          "message": "Customer agreement takes precedence over general policy.",
          "trusted_source": "Northstar Logistics Enterprise Agreement",
          "overridden_source": "Cancellation & Service Credit SOP v4 (Current)"
        }
      ],
      "total_results": 5
    }
    """
```

**Retrieval pipeline:**
```
1. embed(query) → 384-dim vector via SentenceTransformer all-MiniLM-L6-v2
2. ChromaDB.query(where={account_scope: global OR account_id}, n_results=12)
3. For each result:
   weighted_score = (1 - cosine_distance) × AUTHORITY_WEIGHTS[source_type]
4. Sort by weighted_score DESC → take top 5
5. Scan top results for conflicts (current vs deprecated, agreement vs policy)
6. Return structured dict
```

**Authority weights** (from `config.AUTHORITY_WEIGHTS`):
| Source type | Weight |
|---|---|
| customer_agreement | 3.0× |
| current_policy | 2.0× |
| current_sop | 1.8× |
| product_guide | 1.6× |
| deprecated_policy | 0.4× |
| deprecated_sop | 0.3× |

---

### 2.3 `agent/tools/structured_lookup.py`

```python
def lookup(operation: str, params: dict,
           session_account_id: str, is_internal: bool) -> dict:
    """Dispatches to one of:
      get_account_info, get_order, list_orders, get_ticket, list_tickets,
      get_credit_balance, sla_breach_report, proactive_report
    """
```

**Access control enforcement:**
```sql
-- Customer get_order:
SELECT * FROM orders
WHERE order_id = ?
  AND account_id = ?   ← hardcoded session_account_id, never LLM-supplied

-- Internal get_order (all accounts visible):
SELECT * FROM orders WHERE order_id = ?

-- proactive_report only callable when is_internal == True
```

---

### 2.4 `agent/tools/action_executor.py`

**Two-phase protocol:**
```
Phase 1 — request_action(action_type, params, ...) called by orchestrator
  ├── Generates action_id (UUID)
  ├── Stores in _pending dict (in-memory, keyed by action_id)
  └── Returns: {status: "requires_confirmation", action_id: ..., summary: "..."}
       ↑ LLM gets this, tells the user to confirm

Phase 2 — confirm_action(action_id) called by /api/confirm after user clicks Confirm
  ├── Pops from _pending
  ├── Executes the actual DB mutation
  ├── Writes to actions_log
  └── Returns: {status: "executed", result: {...}}
```

**Supported actions:**
| action_type | Parameters | DB mutation |
|---|---|---|
| `cancel_order` | `order_id` | `UPDATE orders SET status='CANCELLED'` |
| `apply_credit` | `amount`, `reason` | `UPDATE accounts SET credit_balance = credit_balance + amount` |
| `update_ticket_status` | `ticket_id`, `new_status` | `UPDATE tickets SET status=?` |
| `escalate_ticket` | `ticket_id`, `description` | Status → 'escalated', description append |
| `close_ticket` | `ticket_id`, `resolution` | Status → 'closed', historical_resolution set |
| `create_escalation` | `subject`, `description`, `priority` | INSERT new ticket row |

---

## 3. Database Schema

```sql
-- parcelpilot.db (populated from ParcelPilot_Data.xlsx)

CREATE TABLE accounts (
    account_id      TEXT PRIMARY KEY,          -- 'ACCT-001', 'ACCT-002', ...
    account_name    TEXT NOT NULL,             -- 'Northstar Logistics', etc.
    plan            TEXT NOT NULL,             -- 'Enterprise' | 'Growth' | 'Standard'
    status          TEXT,                      -- 'active' | 'inactive'
    csm             TEXT,                      -- Customer Success Manager name
    contract_file   TEXT,                      -- reference to agreement PDF
    premium_support INTEGER,                   -- 0 | 1 (SQLite bool)
    notes           TEXT,
    credit_balance  REAL DEFAULT 0.0
);

CREATE TABLE orders (
    order_id                    TEXT PRIMARY KEY,  -- 'ORD-1001', etc.
    account_id                  TEXT NOT NULL REFERENCES accounts(account_id),
    carrier                     TEXT,              -- 'SwiftShip', etc.
    status                      TEXT NOT NULL,     -- 'BOOKED' | 'PICKED_UP' | 'DELIVERED' | 'CANCELLED'
    booked_at                   TEXT,              -- ISO datetime of booking
    pickup_window_start         TEXT,              -- ISO datetime
    pickup_window_end           TEXT,              -- ISO datetime
    pickup_actual_at            TEXT,              -- ISO datetime (null if not yet picked up)
    shipment_fee_inr            INTEGER,           -- fee in Indian Rupees
    carrier_fault               INTEGER,           -- 0 | 1 (SQLite bool)
    customer_fault              INTEGER,           -- 0 | 1 (SQLite bool)
    cancellation_requested_at   TEXT,              -- ISO datetime (null if no request)
    notes                       TEXT
);

CREATE TABLE tickets (
    ticket_id               TEXT PRIMARY KEY,      -- 'TKT-501', etc.
    account_id              TEXT NOT NULL REFERENCES accounts(account_id),
    created_at              TEXT,                  -- ISO datetime
    status                  TEXT NOT NULL,         -- 'open' | 'escalated' | 'closed'
    subject                 TEXT,                  -- short issue summary
    description             TEXT,                  -- full issue description
    channel                 TEXT,                  -- 'email' | 'chat' | 'phone'
    assigned_to             TEXT,                  -- agent name
    last_customer_message_at TEXT,                 -- ISO datetime
    historical_resolution   TEXT                   -- previous resolution (may be wrong — always prefaced with disclaimer)
);

CREATE TABLE actions_log (
    action_id       TEXT PRIMARY KEY,          -- UUID
    account_id      TEXT NOT NULL,
    session_id      TEXT,
    action_type     TEXT NOT NULL,
    parameters      TEXT,                      -- JSON string
    status          TEXT NOT NULL,             -- 'pending' | 'executed' | 'cancelled' | 'failed'
    executed_at     TEXT,
    executed_by     TEXT
);
```

**Important notes:**
- `tickets` has no `priority`, `sla_breach`, or `resolution` columns — SLA breach
  detection is computed at query time by the issue detector, not stored as a flag.
- `orders` has no `estimated_delivery`, `origin`, `destination`, or `tracking_number`.
  The data uses pickup-window logistics, not delivery-tracking logistics.
- `historical_resolution` in `tickets` is always returned with a disclaimer that
  it may not reflect current policy (relevant for TKT-450 and TKT-451).

---

## 4. ChromaDB Collection Schema

**Collection name:** `parcelpilot_docs`
**Embedding model:** `all-MiniLM-L6-v2` (384 dimensions)
**Distance metric:** cosine

**Per-chunk metadata:**
```json
{
  "source_name": "05_Northstar_Logistics_Enterprise_Agreement",
  "display_name": "Northstar Logistics Enterprise Agreement",
  "source_type": "customer_agreement",
  "authority_level": 100,
  "is_deprecated": "false",
  "account_scope": "ACCT-001",
  "chunk_index": 0
}
```

**`account_scope` values:**
- `"global"` — retrieved for all accounts (policy/SOP/product guide docs)
- `"ACCT-001"` — only retrieved when session is ACCT-001 or INTERNAL
- `"ACCT-002"` — only retrieved when session is ACCT-002 or INTERNAL

**Note:** With the source PDFs (99–207 words each), each document produces
exactly 1 chunk at the 500-word chunk size. Total collection size: 6 chunks.

---

## 5. API Contracts (FastAPI — server.py)

### `POST /api/login`
```json
// Request
{ "account_id": "ACCT-001" }

// Response 200
{
  "session_id": "uuid-...",
  "account_id": "ACCT-001",
  "company": "Northstar Logistics",
  "plan": "Enterprise",
  "is_internal": false,
  "snapshot": "2026-08-16 11:00"
}
```

### `POST /api/chat`
```json
// Request
{ "session_id": "uuid-...", "message": "Can I cancel ORD-1001 without a fee?" }

// Response 200
{
  "text": "Yes. Per the Northstar Enterprise Agreement, all BOOKED orders...",
  "tool_calls": [
    {
      "name": "search_documents",
      "inputs": {"query": "cancellation fee Northstar"},
      "output": {
        "results": [{"source": "Northstar Logistics Enterprise Agreement", ...}],
        "conflicts": [{"type": "agreement_override", ...}],
        "total_results": 3
      }
    },
    {
      "name": "lookup_data",
      "inputs": {"operation": "get_order", "params": {"order_id": "ORD-1001"}},
      "output": {"order_id": "ORD-1001", "status": "BOOKED", ...}
    }
  ],
  "pending_action": null
}
```

### `POST /api/confirm`
```json
// Request
{ "session_id": "uuid-...", "action_id": "uuid-...", "confirmed": true }

// Response 200
{
  "text": "Order ORD-1001 has been successfully cancelled.",
  "tool_calls": [],
  "pending_action": null
}
```

### `GET /api/health`
```json
// Response 200
{
  "status": "ok",
  "model": "openai/gpt-oss-120b",
  "ai_configured": true,
  "db": "ok",
  "db_counts": {"accounts": 4, "tickets": 7}
}
```

### `GET /api/stats?session_id=...` (internal sessions only)
```json
{
  "open_tickets": 5,
  "pending_cancels": 3,
  "missed_pickups": 1,
  "accounts": 4
}
```

### `POST /api/logout`
```json
// Response 200
{ "ok": true }
```

---

## 6. Sequence Diagram — Action with Confirmation Gate

```
User          UI              Orchestrator      Groq LLM        Tool C
 │             │                   │                │               │
 │ "Cancel     │                   │                │               │
 │  ORD-1001"  │                   │                │               │
 │────────────▶│                   │                │               │
 │             │── chat(msg) ─────▶│                │               │
 │             │                   │── messages ───▶│               │
 │             │                   │                │ tool_calls:   │
 │             │                   │                │ execute_action│
 │             │                   │◀──────────────│               │
 │             │                   │── request_action() ──────────▶│
 │             │                   │                │               │ returns
 │             │                   │                │               │ {status:
 │             │                   │◀──────────────────────────────│  "requires_
 │             │                   │  (tool_result  │               │  confirmation"
 │             │                   │   to Groq LLM) │               │  action_id: X}
 │             │                   │── messages ───▶│               │
 │             │                   │                │ "I need your  │
 │             │                   │                │  confirmation"│
 │             │                   │◀──────────────│               │
 │             │◀── AgentResponse ─│                │               │
 │             │   pending_action  │                │               │
 │◀───────────│                   │                │               │
 │  See confirm│                   │                │               │
 │  card       │                   │                │               │
 │             │                   │                │               │
 │ ✅ Confirm  │                   │                │               │
 │────────────▶│                   │                │               │
 │             │── /api/confirm ──▶│                │               │
 │             │                   │── confirm_action(X) ─────────▶│
 │             │                   │                │               │ UPDATE orders
 │             │                   │◀──────────────────────────────│ INSERT log
 │             │                   │  {status: executed}           │
 │             │                   │── messages ───▶│               │
 │             │                   │                │ "Order        │
 │             │                   │                │  cancelled!"  │
 │             │                   │◀──────────────│               │
 │             │◀── AgentResponse ─│                │               │
 │◀───────────│                   │                │               │
 │  Final msg  │                   │                │               │
```

---

## 7. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM | Groq API (`openai/gpt-oss-120b`) via OpenAI-compatible SDK | Fast inference, no vendor lock-in via SDK, tool_use format |
| Agent pattern | ReAct (Reason+Act loop) | Multi-step queries need iterative tool chaining |
| Embeddings | SentenceTransformers (local, all-MiniLM-L6-v2) | No extra API key; adequate quality for the 6-document corpus |
| Vector store | ChromaDB (local persistent) | Zero-infra, metadata filtering, account scoping |
| Structured DB | SQLite | Built into Python, portable, no server needed |
| Access control | Tool-layer enforcement (SQL WHERE clause) | LLM prompt injection cannot bypass a hardcoded SQL predicate |
| Confirmation gate | Two-phase (request → confirm) | Irreversible actions need explicit human-in-the-loop |
| Frontend | React + Vite + TypeScript + Tailwind | Modern, type-safe, production-ready SPA with instant HMR |
| Backend | FastAPI (server.py) | Single process serves both API and built frontend |
