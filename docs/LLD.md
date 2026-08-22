# Low-Level Design — ParcelPilot AI Support System

## 1. Module Dependency Graph

```
config.py  (no deps — read by everything)
     │
     ├─▶ ingestion/document_ingester.py  (chromadb, sentence-transformers)
     ├─▶ ingestion/excel_ingester.py     (pandas, sqlite3)
     │
     ├─▶ agent/tools/document_search.py  (chromadb)
     ├─▶ agent/tools/structured_lookup.py (sqlite3)
     ├─▶ agent/tools/action_executor.py   (sqlite3)
     │
     ├─▶ agent/orchestrator.py  (anthropic, all three tools)
     │
     ├─▶ api/main.py      (fastapi, orchestrator)
     └─▶ ui/app.py        (streamlit, orchestrator directly)
```

---

## 2. Class / Module Interfaces

### 2.1 `agent/orchestrator.py`

```python
class Orchestrator:
    account_id: str          # from trusted session
    is_internal: bool
    session_id: str
    messages: list[dict]     # full Claude message history

    def chat(user_message: str) -> AgentResponse
    def notify_confirmation(action_id: str, confirmed: bool) -> AgentResponse
    def reset() -> None

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

**ReAct loop logic:**
```
while iterations < MAX_ITERATIONS:
    response = claude.messages.create(tools=..., messages=history)
    if stop_reason == "end_turn":   → extract text, return
    if stop_reason == "tool_use":
        for each tool_use block:
            result = dispatch_tool(name, inputs)
            if result.status == "requires_confirmation":
                store pending_action, continue loop
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
          "source": "Acme Corp Service Agreement (ACC-001)",
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
          "trusted_source": "Acme Corp Agreement",
          "overridden_source": "General Policy v2.0"
        }
      ],
      "total_results": 5
    }
    """
```

**Retrieval pipeline:**
```
1. embed(query) → 384-dim vector
2. ChromaDB.query(where={account_scope: global OR account_id}, n_results=12)
3. For each result:
   weighted_score = (1 - cosine_distance) × AUTHORITY_WEIGHTS[source_type]
4. Sort by weighted_score DESC → take top 5
5. Scan top results for conflicts (current vs deprecated, agreement vs policy)
6. Return structured dict
```

---

### 2.3 `agent/tools/structured_lookup.py`

```python
def lookup(operation: str, params: dict,
           session_account_id: str, is_internal: bool) -> dict:
    """Dispatches to one of:
      get_account_info, get_order, list_orders,
      get_ticket, list_tickets, get_credit_balance, sla_breach_report
    """
```

**Access control enforcement:**
```sql
-- Customer get_order:
SELECT * FROM orders
WHERE order_id = ?
  AND account_id = ?   ← hardcoded session_account_id, never LLM-supplied

-- Internal get_order (target account must still be specified):
SELECT * FROM orders WHERE order_id = ?
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

Phase 2 — confirm_action(action_id) called by UI/API after user clicks Confirm
  ├── Pops from _pending
  ├── Executes the actual DB mutation
  ├── Writes to actions_log
  └── Returns: {status: "executed", result: {...}}

Alternatively:
  cancel_pending_action(action_id)
  ├── Pops from _pending (no DB writes)
  └── Returns: {status: "cancelled"}
```

**Supported actions:**
| action_type | Parameters | DB mutation |
|-------------|-----------|-------------|
| `cancel_order` | `order_id` | `UPDATE orders SET status='cancelled'` |
| `apply_credit` | `amount`, `reason` | `UPDATE accounts SET credit_balance = credit_balance + amount` |
| `update_ticket_status` | `ticket_id`, `new_status` | `UPDATE tickets SET status=?` |
| `escalate_ticket` | `ticket_id`, `priority` | `UPDATE tickets SET priority=?, status='escalated'` |
| `close_ticket` | `ticket_id`, `resolution` | `UPDATE tickets SET status='resolved', resolution=?` |

---

## 3. Database Schema

```sql
-- parcelpilot.db

CREATE TABLE accounts (
    account_id      TEXT PRIMARY KEY,          -- 'ACC-001', 'ACC-002', 'ACC-003'
    company_name    TEXT NOT NULL,
    plan            TEXT NOT NULL,             -- 'starter' | 'professional' | 'enterprise'
    contact_email   TEXT,
    contract_start  TEXT,                      -- ISO date string
    contract_end    TEXT,
    monthly_volume  INTEGER,
    credit_balance  REAL DEFAULT 0.0,
    status          TEXT DEFAULT 'active'
);

CREATE TABLE orders (
    order_id            TEXT PRIMARY KEY,      -- 'ORD-1001' etc.
    account_id          TEXT NOT NULL REFERENCES accounts(account_id),
    status              TEXT NOT NULL,         -- pending | in_transit | delivered | cancelled
    tracking_number     TEXT,
    origin              TEXT,
    destination         TEXT,
    weight_kg           REAL,
    amount              REAL NOT NULL,
    service_type        TEXT,                  -- standard | express | overnight
    created_at          TEXT,
    delivered_at        TEXT,
    estimated_delivery  TEXT
);

CREATE TABLE tickets (
    ticket_id       TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(account_id),
    order_id        TEXT REFERENCES orders(order_id),
    issue_type      TEXT NOT NULL,             -- billing | delivery | refund | cancellation | account
    status          TEXT NOT NULL,             -- open | in_progress | escalated | resolved
    priority        TEXT DEFAULT 'medium',     -- low | medium | high | critical
    description     TEXT,
    resolution      TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    resolved_at     TEXT,
    sla_breach      INTEGER DEFAULT 0          -- 0 = false, 1 = true (SQLite bool)
);

CREATE TABLE actions_log (
    action_id       TEXT PRIMARY KEY,          -- UUID
    account_id      TEXT NOT NULL,
    session_id      TEXT,
    action_type     TEXT NOT NULL,
    parameters      TEXT,                      -- JSON string
    status          TEXT NOT NULL,             -- pending | executed | cancelled | failed
    executed_at     TEXT,
    executed_by     TEXT
);
```

---

## 4. ChromaDB Collection Schema

**Collection name:** `parcelpilot_docs`
**Embedding model:** `all-MiniLM-L6-v2` (384 dimensions)
**Distance metric:** cosine

**Per-chunk metadata:**
```json
{
  "source_name": "agreement_acme_corp",
  "display_name": "Acme Corp Service Agreement (ACC-001)",
  "source_type": "customer_agreement",
  "authority_level": 100,
  "is_deprecated": "false",
  "account_scope": "ACC-001",
  "chunk_index": 3
}
```

**`account_scope` values:**
- `"global"` — all users can retrieve this chunk (policy/SOP docs)
- `"ACC-001"` — only retrieved when session is ACC-001 or INTERNAL

---

## 5. API Contracts (FastAPI)

### `POST /api/auth/login`
```json
// Request
{ "account_id": "ACC-001" }

// Response 200
{
  "session_id": "uuid-...",
  "account_id": "ACC-001",
  "company_name": "Acme Corp",
  "role": "customer"
}
```

### `POST /api/chat`
```json
// Request
{ "session_id": "uuid-...", "message": "What is my refund window?" }

// Response 200
{
  "text": "According to your Acme Corp Service Agreement...",
  "tool_calls": [
    {
      "name": "search_documents",
      "inputs": {"query": "refund window"},
      "output": { "results": [...], "conflicts": [...] }
    }
  ],
  "pending_action": null,
  "session_id": "uuid-..."
}
```

### `POST /api/confirm`
```json
// Request
{ "session_id": "uuid-...", "action_id": "uuid-...", "confirmed": true }

// Response 200
{
  "text": "Order ORD-1003 has been successfully cancelled.",
  "tool_calls": [],
  "session_id": "uuid-..."
}
```

---

## 6. Sequence Diagram — Action with Confirmation Gate

```
User          UI              Orchestrator        Claude          Tool C
 │             │                   │                │               │
 │ "Cancel     │                   │                │               │
 │  ORD-1003"  │                   │                │               │
 │────────────▶│                   │                │               │
 │             │── chat(msg) ─────▶│                │               │
 │             │                   │── messages ───▶│               │
 │             │                   │                │ tool_use:     │
 │             │                   │                │ execute_action│
 │             │                   │◀──────────────│               │
 │             │                   │── request_action() ──────────▶│
 │             │                   │                │               │ returns
 │             │                   │                │               │ {status:
 │             │                   │◀──────────────────────────────│  "requires_
 │             │                   │  (tool_result  │               │  confirmation"
 │             │                   │   to Claude)   │               │  action_id: X}
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
 │             │── confirm(X) ────▶│                │               │
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
|----------|--------|-----------|
| LLM | Claude claude-sonnet-4-6 | Native tool_use, strong instruction following, context length |
| Agent pattern | ReAct (Reason+Act loop) | Multi-step queries need iterative tool chaining |
| Embeddings | SentenceTransformers (local) | No extra API key; adequate quality for demo corpus |
| Vector store | ChromaDB (local persistent) | Zero-infra, metadata filtering, easy to deploy |
| Structured DB | SQLite | Built into Python, portable, no server needed |
| Access control | Tool-layer enforcement | LLM prompt injection cannot bypass SQL WHERE clause |
| Confirmation gate | Two-phase (request → confirm) | Irreversible actions need explicit human-in-the-loop |
| Frontend | Streamlit | Fastest path to a polished chat demo |
| Backend | FastAPI | Optional REST layer; enables future multi-client support |
