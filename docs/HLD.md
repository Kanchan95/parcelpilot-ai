# High-Level Design — ParcelPilot AI Support System

## 1. System Overview

ParcelPilot AI is a multi-tool conversational agent that handles customer and
internal-ops support requests for a logistics platform. It replaces manual ticket
processing with an AI agent that reasons over policy documents AND structured data,
executes actions only after explicit confirmation, and enforces strict per-account
data isolation.

---

## 2. System Context

```
┌────────────────────────────────────────────────────────────────────────┐
│                          External Users                                │
│                                                                        │
│   ┌──────────────────┐              ┌───────────────────────────────┐  │
│   │  Customer        │              │  Internal Ops Agent           │  │
│   │  (web/chat)      │              │  (same UI, elevated access)   │  │
│   └────────┬─────────┘              └──────────────┬────────────────┘  │
└────────────┼──────────────────────────────────────┼────────────────────┘
             │  HTTPS                               │  HTTPS
┌────────────▼──────────────────────────────────────▼────────────────────┐
│                     ParcelPilot AI Application                         │
│                                                                        │
│  ┌─────────────────┐     ┌──────────────────┐    ┌───────────────────┐│
│  │  Streamlit UI   │────▶│   FastAPI Layer  │───▶│  Orchestrator     ││
│  │  (chat, tools,  │     │  (session mgmt,  │    │  (ReAct loop,     ││
│  │   confirm gate) │     │   REST endpoints)│    │   Claude LLM)     ││
│  └─────────────────┘     └──────────────────┘    └──────┬────────────┘│
│                                                          │             │
│           ┌──────────────────────────────────────────────┤             │
│           │              Three Agent Tools               │             │
│  ┌────────▼──────┐   ┌────────────────┐   ┌────────────▼───────────┐ │
│  │  Tool A       │   │   Tool B       │   │   Tool C               │ │
│  │  Doc Search   │   │  Struct Lookup │   │  Action Executor       │ │
│  │  (RAG+rerank) │   │  (SQL+ACL)     │   │  (2-phase confirm)     │ │
│  └────────┬──────┘   └───────┬────────┘   └────────────┬───────────┘ │
│           │                  │                          │             │
│  ┌────────▼──────┐   ┌───────▼────────┐   ┌────────────▼───────────┐ │
│  │  ChromaDB     │   │   SQLite DB    │   │   SQLite DB            │ │
│  │  (vectors)    │   │   (accounts,   │   │   (actions_log)        │ │
│  │               │   │   orders,      │   │                        │ │
│  └───────────────┘   │   tickets)     │   └────────────────────────┘ │
│                      └────────────────┘                              │
└────────────────────────────────────────────────────────────────────────┘

External Dependencies:
  - Anthropic API (Claude claude-sonnet-4-6) — LLM inference
  - SentenceTransformers (all-MiniLM-L6-v2) — local embeddings, no external API needed
```

---

## 3. Component Overview

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| **Streamlit UI** | Chat interface, tool activity sidebar, confirmation dialogs | Streamlit 1.40+ |
| **FastAPI Layer** | Session management, REST API, CORS | FastAPI + Uvicorn |
| **Orchestrator** | ReAct loop, tool dispatch, message history | Anthropic SDK (tool_use) |
| **Tool A — Document Search** | RAG over policy docs and agreements | ChromaDB + SentenceTransformers |
| **Tool B — Structured Lookup** | Account/order/ticket queries with ACL | SQLite (Python built-in) |
| **Tool C — Action Executor** | State changes with two-phase confirmation | SQLite writes |
| **Ingestion Pipeline** | Document chunking, embedding, Excel→SQLite | ChromaDB, pandas, openpyxl |

---

## 4. Data Flow — Customer Asks a Multi-Step Question

```
User: "Can I cancel ORD-1003 and get a refund?"
        │
        ▼
[1] Auth Layer
    Resolves account_id = ACC-001 from session (trusted, not from user input)
        │
        ▼
[2] Orchestrator sends to Claude with tool definitions
    Claude reasons: "I need to check (a) cancellation policy and (b) order status
                    before I can cancel anything."
        │
        ├──[Tool A call]──▶ search_documents("cancellation policy refund")
        │                        ├── Retrieves current policy: "free within 24h, 10% after"
        │                        ├── Retrieves Acme Corp agreement: "free within 48h, 5% after"
        │                        └── Conflict detected: agreement overrides general policy
        │
        ├──[Tool B call]──▶ lookup_data("get_order", {order_id: "ORD-1003"})
        │                        ├── WHERE account_id = 'ACC-001' AND order_id = 'ORD-1003'
        │                        └── Returns: {status: "pending", created_at: today, amount: 2200}
        │
        Claude reasons: "Order is pending and created today → within 48h free cancel window
                        per Acme Corp agreement. Safe to proceed."
        │
        ├──[Tool C call]──▶ execute_action("cancel_order", {order_id: "ORD-1003"})
        │                        └── Returns: {status: "requires_confirmation", summary: "Cancel ORD-1003..."}
        │
[3] Orchestrator pauses — returns pending_action to UI
        │
        ▼
[4] Streamlit shows confirmation card:
    "I'm about to cancel ORD-1003 (free cancellation per your agreement). Confirm?"
        │
        ├── User clicks ✅ Confirm
        │       │
        │       ▼
        │   action_executor.confirm_action(action_id)
        │       ├── UPDATE orders SET status='cancelled' WHERE order_id='ORD-1003' AND account_id='ACC-001'
        │       └── INSERT INTO actions_log ...
        │       │
        │       ▼
        │   Orchestrator re-enters with result → Claude writes final response
        │
        └── User clicks ❌ Cancel → no changes made, user notified
```

---

## 5. Access Control Design

```
┌─────────────────────────────────────────────────────────┐
│                  DEFENSE IN DEPTH                       │
│                                                         │
│  Layer 1 — Session (Auth)                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ POST /api/auth/login → returns session_id        │   │
│  │ session_id maps to account_id in server memory   │   │
│  │ All subsequent calls carry session_id            │   │
│  └─────────────────────────────────────────────────┘   │
│                          │                              │
│  Layer 2 — Tool Level (cannot be bypassed by LLM)      │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Tool B: ALL SQL queries include                  │   │
│  │   AND account_id = :session_account_id           │   │
│  │ This is hardcoded in the tool — the LLM's        │   │
│  │ tool input never carries account_id              │   │
│  │                                                  │   │
│  │ Tool A: ChromaDB WHERE filter:                   │   │
│  │   account_scope = 'global'                       │   │
│  │   OR account_scope = session_account_id          │   │
│  │ → Customer can't read another account's          │   │
│  │   service agreement                              │   │
│  │                                                  │   │
│  │ Tool C: action always targets session_account_id │   │
│  └─────────────────────────────────────────────────┘   │
│                          │                              │
│  Layer 3 — Audit Log                                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Every executed action → actions_log table        │   │
│  │ Fields: who, what, when, session_id              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Source Trust Hierarchy

```
Priority (highest → lowest)

  ★★★  Customer Service Agreement
       e.g., Acme Corp Agreement — overrides ALL general policy
       authority_level = 100, weight = 3.0×

  ★★   Current Official Policy (Policy v2.0)
       authority_level = 70, weight = 2.0×

  ★★   Current SOP (SOP v3.0)
       authority_level = 60, weight = 1.8×

  ★    Deprecated Policy (Policy v1.0 — superseded Jan 2024)
       authority_level = 20, weight = 0.4×
       → Always disclosed as deprecated when cited

  ★    Deprecated SOP (SOP v1.5 — superseded Feb 2024)
       authority_level = 15, weight = 0.3×

Re-ranking formula:
  weighted_score = cosine_similarity × authority_weight
  → A less relevant Agreement chunk beats a highly relevant Deprecated Policy chunk
```

---

## 7. Deployment Architecture (Production Target)

```
┌──────────────────────────────────────────────────────────┐
│  Cloud Deployment                                        │
│                                                          │
│  ┌────────────────┐    ┌──────────────────────────────┐  │
│  │  Vercel /      │    │  Railway / Render             │  │
│  │  Streamlit     │───▶│  FastAPI + Uvicorn            │  │
│  │  Cloud (UI)    │    │  (2 workers)                  │  │
│  └────────────────┘    └──────────────┬───────────────┘  │
│                                        │                  │
│                          ┌─────────────▼──────────────┐  │
│                          │  Persistent Volume          │  │
│                          │  .chromadb/ (vectors)       │  │
│                          │  parcelpilot.db (SQLite)    │  │
│                          └────────────────────────────┘  │
│                                                          │
│  External: Anthropic API (claude-sonnet-4-6)             │
└──────────────────────────────────────────────────────────┘

Demo (local):
  Terminal 1: streamlit run ui/app.py
  Terminal 2 (optional): uvicorn api.main:app --reload
```

---

## 8. Optional Feature — Proactive Issue Detection

The `lookup_data` tool supports `sla_breach_report` which internal agents can use
to surface all tickets with `sla_breach = TRUE`. In the full implementation this
would run on a schedule and cluster tickets by `issue_type` to identify patterns
(e.g., "12 billing disputes in the past 30 days, up from 3").
