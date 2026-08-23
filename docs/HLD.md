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
             │  HTTP                                │  HTTP
┌────────────▼──────────────────────────────────────▼────────────────────┐
│                     ParcelPilot AI Application                         │
│                                                                        │
│  ┌─────────────────┐     ┌──────────────────┐    ┌───────────────────┐│
│  │  React/Vite UI  │────▶│  FastAPI Backend  │───▶│  Orchestrator     ││
│  │  (chat, tools,  │     │  (session mgmt,   │    │  (ReAct loop,     ││
│  │   confirm gate) │     │   REST endpoints) │    │   Groq LLM)       ││
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
  - Groq API (openai/gpt-oss-120b) — LLM inference via OpenAI-compatible SDK
  - SentenceTransformers (all-MiniLM-L6-v2) — local embeddings, no external API needed
```

---

## 3. Component Overview

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| **React/Vite UI** | Chat interface, tool activity sidebar, confirmation dialogs, source citations | React 18 + Vite 5 + TypeScript + Tailwind CSS |
| **FastAPI Backend** | Session management, REST API, SPA serving, CORS | FastAPI + Uvicorn (server.py) |
| **Orchestrator** | ReAct loop, tool dispatch, message history | OpenAI SDK (Groq endpoint, tool_use format) |
| **Tool A — Document Search** | RAG over policy docs and agreements | ChromaDB + SentenceTransformers |
| **Tool B — Structured Lookup** | Account/order/ticket queries with ACL | SQLite (Python built-in) |
| **Tool C — Action Executor** | State changes with two-phase confirmation | SQLite writes |
| **Ingestion Pipeline** | Document chunking, embedding, Excel→SQLite | ChromaDB, pandas, openpyxl, pdfplumber |

---

## 4. Data Flow — Customer Asks a Multi-Step Question

```
User: "Can I cancel ORD-1001 without a cancellation fee?"
        │
        ▼
[1] Auth Layer
    Resolves account_id = ACCT-001 from session (trusted, not from user input)
        │
        ▼
[2] Orchestrator sends to Groq LLM with tool definitions
    LLM reasons: "I need to check (a) cancellation policy and (b) order status
                  to give a definitive YES/NO."
        │
        ├──[Tool A call]──▶ search_documents("cancellation policy fee Northstar")
        │                        ├── Retrieves Northstar Enterprise Agreement
        │                        │   (account_scope=ACCT-001, authority 3.0×)
        │                        ├── Retrieves Cancellation SOP v4 (current, 1.8×)
        │                        └── Agreement override conflict detected:
        │                            Northstar agreement waives all pre-pickup fees
        │
        ├──[Tool B call]──▶ lookup_data("get_order", {order_id: "ORD-1001"})
        │                        ├── WHERE account_id = 'ACCT-001' AND order_id = 'ORD-1001'
        │                        └── Returns: {status: "BOOKED", pickup_actual_at: null}
        │
        LLM reasons: "Order is BOOKED and not yet picked up. Northstar agreement
                      waives all cancellation fees for any BOOKED shipment.
                      Answer: YES, no fee."
        │
        ▼
[3] Orchestrator returns final response with tool_calls and source attribution
        │
        ▼
[4] React UI renders response with collapsible Sources panel showing:
    - Northstar Enterprise Agreement (Customer Agreement, Authority 100)
    - Cancellation & Service Credit SOP v4 (Current SOP, Authority 65)
    - ⚠️ Agreement override: customer agreement takes precedence over general policy
```

---

## 5. Access Control Design

```
┌─────────────────────────────────────────────────────────┐
│                  DEFENSE IN DEPTH                       │
│                                                         │
│  Layer 1 — Session (Auth)                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ POST /api/login → returns session_id             │   │
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
       e.g., Northstar Enterprise Agreement — overrides ALL general policy
       authority_level = 100, weight = 3.0×

  ★★   Current Official Policy (Support Policy v3)
       authority_level = 70, weight = 2.0×

  ★★   Current SOP (Cancellation & Service Credit SOP v4)
       authority_level = 65, weight = 1.8×

  ★    Product Operations Guide (Known Issues: KI-208, KI-211)
       authority_level = 60, weight = 1.6×

  ★    Deprecated Policy (Support Policy v2 — superseded)
       authority_level = 20, weight = 0.4×
       → Always disclosed as deprecated when cited

  ★    Deprecated SOP (any superseded SOP)
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
│  ┌────────────────────────────────────────────────────┐  │
│  │  Railway / Render / Fly.io                         │  │
│  │  FastAPI + Uvicorn (python server.py)              │  │
│  │  Serves React SPA from web/dist/ + /api/* routes  │  │
│  └──────────────────────┬─────────────────────────────┘  │
│                         │                                │
│           ┌─────────────▼──────────────┐                │
│           │  Persistent Volume          │                │
│           │  .chromadb/ (vectors)       │                │
│           │  parcelpilot.db (SQLite)    │                │
│           └────────────────────────────┘                │
│                                                          │
│  External: Groq API (openai/gpt-oss-120b)                │
│            GROQ_API_KEY in environment                   │
└──────────────────────────────────────────────────────────┘

Local demo (single command after setup):
  python server.py   →  http://localhost:8080

Development (hot-reload):
  Terminal 1: python server.py
  Terminal 2: cd web && npm run dev   →  http://localhost:3000
```

---

## 8. Optional Feature — Proactive Issue Detection

`agent/analysis/issue_detector.py` implements 5 detectors that run over the full
database when an internal agent calls `lookup_data(operation="proactive_report")`:

- **SLA breach detection**: tickets past their first-response deadline per plan
- **Missed pickup detection**: BOOKED orders past pickup window with no actual pickup
- **Complaint cluster detection**: recurring issues by subject keyword
- **Stale resolution detection**: closed tickets whose historical resolution contradicts
  the current policy (e.g., TKT-450: fee applied to Northstar cancel — wrong per agreement)
- **Pending cancellation detection**: orders with `cancellation_requested_at` not yet actioned

Returns a structured markdown digest. Only accessible to `is_internal` sessions.
