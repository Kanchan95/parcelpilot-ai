# ParcelPilot AI Support System

> **CalQuity — AI Engineer Assessment**
> FastAPI · React/Vite · Groq LLM · ChromaDB · SQLite

---

## Overview

ParcelPilot's ops team manually handles hundreds of weekly support tickets —
cancellations, credits, policy questions, and order queries across multiple
overlapping data sources, some of which are outdated or customer-specific.

This project replaces that manual workflow with a **multi-tool AI agent** that:

- Answers natural-language questions using only the supplied assessment documents and data
- Enforces per-account data isolation at the SQL layer (no cross-account leaks)
- Chains three tools in a single response: document search → data lookup → action
- Never executes a state-changing action without explicit user confirmation
- Detects and discloses conflicts between current and deprecated sources
- Distinguishes customer-specific agreement terms from general policy
- Handles both customer-facing and internal-ops workflows from a single UI

---

## Live Demo

- **GitHub:** https://github.com/Kanchan95/parcelpilot-ai
- **Hosted App (Try the Agent):** https://parcelpilot-ai-mdbx.onrender.com
- **Demo Video:** https://youtu.be/RoPsUHLMizs

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       React / Vite UI (TypeScript)                      │
│   login · chat bubbles · tool chips · Sources panel · confirm dialogs   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP
                         ┌───────▼────────┐
                         │  FastAPI       │  session_id → account_id
                         │  server.py     │  (enforced in every tool call)
                         └───────┬────────┘
                                 │
                    ┌────────────▼─────────────────────────────┐
                    │           Orchestrator                    │
                    │  Groq LLM (openai/gpt-oss-120b)          │
                    │  OpenAI-compatible SDK · ReAct loop       │
                    └────┬──────────────┬───────────────┬──────┘
                         │              │               │
               ┌─────────▼──┐  ┌────────▼──────┐  ┌───▼──────────────┐
               │  Tool A    │  │   Tool B      │  │   Tool C         │
               │  Document  │  │  Structured   │  │  Action Executor │
               │  Search    │  │  Data Lookup  │  │  (2-phase gate)  │
               │  (RAG)     │  │  (SQL + ACL)  │  │                  │
               └─────────┬──┘  └────────┬──────┘  └───┬──────────────┘
                         │              │               │
               ┌─────────▼──┐  ┌────────▼──────┐  ┌───▼──────────────┐
               │ ChromaDB   │  │ SQLite        │  │ SQLite           │
               │ (vectors + │  │ accounts      │  │ actions_log      │
               │  metadata) │  │ orders        │  │                  │
               └────────────┘  │ tickets       │  └──────────────────┘
                               └───────────────┘
  Documents ingested (real assessment PDFs):
  · 01_Support_Policy_v3_CURRENT.pdf          (current policy, authority 2.0×)
  · 02_Support_Policy_v2_DEPRECATED.pdf       (deprecated, authority 0.4×) ← flagged
  · 03_Cancellation_and_Service_Credit_SOP_v4 (current SOP, authority 1.8×)
  · 04_Product_Operations_Guide_and_Known_Issues (product guide, authority 1.6×)
  · 05_Northstar_Logistics_Enterprise_Agreement (authority 3.0×, scoped to ACCT-001)
  · 06_LumenWorks_Service_Agreement             (authority 3.0×, scoped to ACCT-002)
```

---

## Repository Structure

```
parcelpilot-ai/
├── server.py                       # Active FastAPI server (port 8080)
├── config.py                       # All constants & env vars
├── requirements.txt
├── .env.example
├── setup.sh                        # One-command setup
├── ARCHITECTURE.md                 # Architecture decisions and trade-offs
├── PRODUCT_NOTE.md                 # Product design notes and optional features
├── AI_TOOL_DISCLOSURE.md           # AI tool usage disclosure
│
├── docs/
│   ├── HLD.md                      # High-Level Design
│   └── LLD.md                      # Low-Level Design
│
├── data/
│   ├── documents/                  # 6 assessment PDF documents
│   └── structured/
│       └── ParcelPilot_Assessment_Data.xlsx   # authoritative assessment data
│
├── ingestion/
│   ├── document_ingester.py        # Chunks PDFs, embeds, stores in ChromaDB
│   └── excel_ingester.py           # Excel → SQLite (accounts, orders, tickets)
│
├── agent/
│   ├── orchestrator.py             # ReAct loop via Groq API
│   ├── analysis/
│   │   └── issue_detector.py       # Proactive SLA + pattern detection
│   └── tools/
│       ├── document_search.py      # Tool A: RAG + authority re-ranking
│       ├── structured_lookup.py    # Tool B: SQL queries + access control
│       └── action_executor.py      # Tool C: two-phase confirmation gate
│
├── web/                            # React/Vite frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatApp.tsx         # Main chat interface
│   │   │   ├── MessageBubble.tsx   # Message + Sources panel
│   │   │   ├── Sidebar.tsx         # Quick prompts + tool activity
│   │   │   └── LoginPage.tsx       # Account selector
│   │   ├── types.ts
│   │   └── api.ts
│   └── dist/                       # Production build (served by FastAPI)
│
└── tests/
    ├── conftest.py                      # Test DB isolation fixture
    ├── test_assessment_scenarios.py     # Primary scenario regression tests (51 total)
    ├── test_access_control.py           # Cross-account blocking, scoped queries
    └── test_tools.py                    # Tool unit tests + trust hierarchy
```

---

## Setup

### Prerequisites
- Python 3.10+
- A Groq API key — [get one free at console.groq.com](https://console.groq.com)
- Node 18+ (for building the frontend)

### Quick Start (automated)

```bash
git clone https://github.com/Kanchan95/parcelpilot-ai.git
cd parcelpilot-ai
bash setup.sh
```

The setup script:
1. Creates a Python virtual environment
2. Installs all dependencies
3. Loads the real assessment Excel data into SQLite
4. Chunks and embeds the 6 assessment PDFs into ChromaDB
   *(downloads `all-MiniLM-L6-v2` ~80 MB on first run)*
5. Builds the React frontend (requires Node 18+)

Then add your Groq API key:

```bash
# Edit .env and set:
GROQ_API_KEY=your_groq_key_here
```

### Run the App

```bash
source .venv/bin/activate
python server.py
# → http://localhost:8080
```

This serves the built React frontend **and** all `/api/*` routes from a single process.

### Development Mode (hot-reload UI)

```bash
# Terminal 1 — backend
python server.py

# Terminal 2 — frontend with hot reload
cd web && npm run dev
# → http://localhost:3000   (proxies /api → localhost:8080)
```

### Run Tests

```bash
pytest tests/ -v
# Expected: 51 passed
```

Tests use a session-scoped temp copy of the database — the real `parcelpilot.db` is never mutated.

---

## How It Works

### The Three Agent Tools

| Tool | When the agent uses it | What it does |
|------|------------------------|--------------|
| **search_documents** | Policy questions, SLA terms, cancellation rules, credit eligibility | Embeds the query, searches ChromaDB with account-scope filter, re-ranks by `cosine_similarity × authority_weight` |
| **lookup_data** | Order status, credit balance, ticket history, account info, SLA breach report | SQL query against SQLite — always filtered by `session_account_id` (hardcoded, not LLM-supplied) |
| **execute_action** | Cancel order, apply credit, escalate/close ticket | Phase 1: returns confirmation summary. Phase 2: executes only after user clicks Confirm |

### Source Trust Hierarchy

When two documents say different things, the agent follows this order:

```
1. Customer Service Agreement     (weight 3.0×)  ← always wins
   e.g., Northstar Enterprise Agreement overrides the general SOP

2. Current Policy v3              (weight 2.0×)
3. Current SOP v4                 (weight 1.8×)
4. Product Operations Guide       (weight 1.6×)
5. Deprecated Policy v2           (weight 0.4×)  ← flagged as deprecated when cited
6. Deprecated SOP                 (weight 0.3×)  ← flagged as deprecated when cited
```

Re-ranking formula: `score = cosine_similarity × authority_weight`

The agent always discloses conflicts. If a customer agreement differs from the general
policy, the response explicitly states both and says which one applies.

### Access Control

Access control is enforced at the **tool layer**, not just the UI:

- Every SQL query appends `AND account_id = session_account_id` (hardcoded — the LLM cannot override it)
- ChromaDB retrieval filters: `account_scope = 'global' OR account_scope = session_account_id`
- A customer logged in as ACCT-001 (Northstar) cannot read ACCT-002's (LumenWorks) orders, tickets, or service agreement — even by name
- Internal agents bypass account scoping but all their actions are audit-logged

### Confirmation Gate

```
User: "Cancel ORD-1001"
         │
         ▼
Agent calls execute_action("cancel_order", {"order_id": "ORD-1001"})
         │
         ▼
Tool returns: {status: "requires_confirmation", summary: "Cancel ORD-1001..."}
         │
         ▼
UI shows confirmation card → user clicks ✅ Confirm
         │
         ▼
/api/confirm → confirm_action(action_id)
             → UPDATE orders SET status='CANCELLED'
             → INSERT INTO actions_log
         │
         ▼
Agent writes final response: "ORD-1001 has been cancelled."
```

The action is **never** executed before the user clicks Confirm.

---

## Demo Accounts

| Account ID | Company | Plan |
|---|---|---|
| ACCT-001 | Northstar Logistics | Enterprise |
| ACCT-002 | LumenWorks | Growth |
| ACCT-003 | Beacon Retail | Standard |
| ACCT-004 | Axis Labs | Enterprise |
| INTERNAL | ParcelPilot Ops | — (full access) |

---

## Demo Scenarios

Run these in the UI to demonstrate all key features:

### 1. Agreement override — fee-free cancellation (Tools A + B)
Login as **Northstar Logistics (ACCT-001)**
```
Can I cancel ORD-1001 without a cancellation fee?
```
Expected: Agent retrieves Northstar Enterprise Agreement (3.0× authority) AND
the general Cancellation SOP. Conflict detected: agreement overrides SOP.
ORD-1001 is BOOKED and not yet picked up. Answer: **YES, no fee** (Northstar agreement
waives all fees for any BOOKED shipment before pickup, regardless of time elapsed).

### 2. Service credit eligibility — account-specific terms (Tools A + B)
Login as **LumenWorks (ACCT-002)**
```
Is ORD-2002 eligible for a service credit?
```
Expected: LumenWorks agreement retrieved (3.0×) alongside general SOP. ORD-2002
has `carrier_fault=1`, pickup was missed by >4 hours. LumenWorks agreement specifies
a fixed INR 300 credit for this scenario (overrides the general SOP's INR 500/10% cap).
Answer: **YES, INR 300** per LumenWorks agreement.

### 3. Cross-account access block (access control)
Login as **Northstar Logistics (ACCT-001)** and ask:
```
Show me order ORD-2001
```
Expected: "Order ORD-2001 not found or not accessible for this account."
(ORD-2001 belongs to ACCT-002; the SQL `WHERE account_id='ACCT-001'` blocks it.)

### 4. Multi-step escalation — P1 ticket (Tools A + B + C)
Login as **Northstar Logistics (ACCT-001)**
```
Status of TKT-501?
```
Expected: Agent retrieves TKT-501 (P1: all shipment creation failing, HTTP 500).
Checks SLA policy. Recommends immediate escalation. Requests confirmation before
updating ticket status.

### 5. Known issue lookup — product guide (Tool A)
Login as **LumenWorks (ACCT-002)**
```
Why is bulk CSV upload failing for a 4,200-row file?
```
Expected: Product Operations Guide retrieved (KI-208: bulk upload fails for >3,000
rows due to a known bug; workaround: split into batches under 3,000). Conflict
detection: may also surface deprecated policy if present.

### 6. Internal proactive report (Tool B + issue detector)
Login as **Internal Agent**
```
Show proactive issue report
```
Expected: Digest surfaces SLA-breached tickets, missed pickups, pending cancellations,
stale resolutions (including TKT-450 where INR 250 fee was incorrectly applied to
a Northstar cancel — violates their agreement).

---

## Optional Features Built

### Proactive Issue Detection (`agent/analysis/issue_detector.py`)
Analyses the full database to surface:
- **SLA breach detection**: open tickets past their first-response deadline per plan
- **Missed pickup detection**: BOOKED orders past pickup window with no actual pickup
- **Complaint cluster detection**: recurring issue keywords
- **Stale resolution detection**: closed tickets with historical resolutions that
  contradict current policy
- **Pending cancellation detection**: orders with unactioned cancellation requests

Returns a structured markdown digest. Available only to internal agents via
`lookup_data(operation="proactive_report")`.

### Trust & Reliability Disclosures
Built into the document search tool and agent system prompt:
- Every deprecated chunk is tagged `is_deprecated=true` in ChromaDB metadata
- Authority-weighted re-ranking ensures deprecated docs lose to current ones
- Conflict detection surfaces both the trusted and overridden source explicitly
- Historical ticket resolutions always returned with "may not reflect current policy" disclaimer

---

## Tech Stack Rationale

| Choice | Why |
|--------|-----|
| **Groq API (openai/gpt-oss-120b)** | Fast inference; OpenAI-compatible tool_use format works with the standard `openai` SDK |
| **OpenAI SDK (not Anthropic SDK)** | Groq's API speaks the OpenAI chat completions format; vendor-neutral SDK |
| **SentenceTransformers (local)** | No second API key; `all-MiniLM-L6-v2` is fast and accurate for this 6-document corpus |
| **ChromaDB** | Persistent local vector store with metadata filtering — zero external infra |
| **SQLite** | Built into Python, portable, no DB server for assessment/demo |
| **Access control at tool layer** | LLM prompt injection cannot bypass a SQL `WHERE account_id = ?` clause |
| **Two-phase confirmation** | Irreversible actions (cancel, credit) must have human in the loop |
| **React + Vite** | Type-safe, hot-reload, production-optimised SPA — modern and fast |
| **FastAPI** | Serves both the API and the built React SPA from a single process |

---

## API Reference

```
POST  /api/login    { account_id }                           → { session_id, company, plan, is_internal, snapshot }
POST  /api/chat     { session_id, message }                  → { text, tool_calls, pending_action }
POST  /api/confirm  { session_id, action_id, confirmed }     → { text, tool_calls, pending_action }
GET   /api/stats    ?session_id=...                          → { open_tickets, pending_cancels, ... }
POST  /api/logout   { session_id }                           → { ok }
GET   /api/health                                            → { status, model, ai_configured, db }
```

---

## Assessment Deliverables

| Deliverable | Status |
|---|---|
| Public repository with setup instructions | ✅ [github.com/Kanchan95/parcelpilot-ai](https://github.com/Kanchan95/parcelpilot-ai) |
| Hosted application | ✅ [parcelpilot-ai-mdbx.onrender.com](https://parcelpilot-ai-mdbx.onrender.com) |
| 5-minute demo video | ✅ [youtu.be/RoPsUHLMizs](https://youtu.be/RoPsUHLMizs) |
| Architecture note | ✅ [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| High-Level Design | ✅ [`docs/HLD.md`](docs/HLD.md) |
| Low-Level Design | ✅ [`docs/LLD.md`](docs/LLD.md) |
| Product note | ✅ [`PRODUCT_NOTE.md`](PRODUCT_NOTE.md) |
| AI tool usage disclosure | ✅ [`AI_TOOL_DISCLOSURE.md`](AI_TOOL_DISCLOSURE.md) |
