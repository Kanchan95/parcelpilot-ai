# Implementation Plan — ParcelPilot AI

## Phase 0: Setup (Day 1)
- [ ] Initialize Git repo, push to GitHub (public)
- [ ] Set up virtual environment + requirements.txt
- [ ] Obtain/verify access to: Anthropic API key (or OpenAI), vector store library
- [ ] Create `.env.example` with required keys listed

## Phase 1: Data Ingestion (Day 1–2)
- [ ] Place the 4 policy/SOP docs and 2 agreements in `data/documents/`
- [ ] Place Excel file(s) in `data/structured/`
- [ ] Write `ingest_documents.py`:
  - [ ] Read/parse each document (PyPDF2, docx, or plain text)
  - [ ] Chunk into ~500 token segments with overlap
  - [ ] Tag each chunk: `source_name`, `source_type`, `authority_level`, `is_deprecated`, `account_scope` (global or account-specific)
  - [ ] Embed + store in ChromaDB
- [ ] Write `ingest_excel.py`:
  - [ ] Load Excel sheets into pandas DataFrames
  - [ ] Save to SQLite with proper schema
  - [ ] Validate foreign keys (orders.account_id → accounts.account_id)

## Phase 2: Tools (Day 2–3)
- [ ] Implement `tools/document_search.py`:
  - [ ] Query function: embed input → ChromaDB similarity search → re-rank by authority
  - [ ] Returns: List of `{content, source, authority_level, is_deprecated}`
- [ ] Implement `tools/structured_lookup.py`:
  - [ ] Pre-defined query functions: `get_account_info`, `get_order_status`, `list_open_tickets`
  - [ ] All queries hard-filter on `account_id`
  - [ ] Returns: Typed dict or None
- [ ] Implement `tools/action_executor.py`:
  - [ ] Actions: cancel_order, apply_credit, update_ticket, escalate_ticket
  - [ ] Returns two-phase: `{status: "pending_confirmation", summary: "..."}` → after confirm → `{status: "executed", result: "..."}`

## Phase 3: Orchestrator Agent (Day 3–4)
- [ ] Write `agent/orchestrator.py`:
  - [ ] System prompt: role, tool descriptions, trust hierarchy, confirmation rule
  - [ ] Tool binding (LangChain / raw Anthropic tool-use)
  - [ ] ReAct loop: call LLM → parse tool calls → execute tools → feed back observations → repeat
  - [ ] Confirmation gate: if Tool C returns `pending_confirmation`, pause and surface to user
  - [ ] Conflict detection: if multiple tool results have conflicting info, build disclosure statement
- [ ] Write `agent/auth.py`:
  - [ ] Session → account_id resolution
  - [ ] Internal agent role flag

## Phase 4: API (Day 4)
- [ ] Write `api/main.py` (FastAPI):
  - [ ] `POST /chat` — takes `{session_id, message}`, returns `{response, tools_used, sources, confirmation_required?}`
  - [ ] `POST /confirm` — takes `{session_id, action_id}`, executes the pending action
  - [ ] `POST /auth/login` — simple mock auth, returns session token with account_id

## Phase 5: UI (Day 4–5)
- [ ] Write `ui/app.py` (Streamlit):
  - [ ] Login screen (enter account ID or "internal agent")
  - [ ] Chat window with message history
  - [ ] Tool activity sidebar (shows which tools were called per turn)
  - [ ] Confirmation dialog (modal or inline) before state-changing actions
  - [ ] Source citations shown below each response
  - [ ] Conflict/uncertainty disclosures shown in yellow/orange

## Phase 6: Optional Features (Day 5–6)
- [ ] Proactive Issue Detection:
  - [ ] `analysis/issue_detector.py`: cluster tickets, check SLA, detect anomalies
  - [ ] Surface digest in internal agent UI
- [ ] Trust Reliability Display:
  - [ ] Make conflict disclosures more prominent in UI
  - [ ] Add "Why did I answer this way?" explainability panel

## Phase 7: Demo & Submission (Day 6–7)
- [ ] Deploy to Railway / Render (backend) + Streamlit Cloud (UI)
- [ ] Record 5-minute demo video:
  1. Architecture overview (1 min)
  2. Multi-step query demo — all 3 tools (1.5 min)
  3. Confirmation gate demo (30 sec)
  4. Access control demo — blocked cross-account attempt (30 sec)
  5. Source conflict resolution demo (30 sec)
  6. Key design decisions (1 min)
- [ ] Write ARCHITECTURE.md (agent/tool design, conflict handling) ✓
- [ ] Write PRODUCT_NOTE.md (additional problems, metrics) ✓
- [ ] Write AI_TOOL_DISCLOSURE.md (list of AI tools used in building this)
- [ ] Final README polish ✓

---

## Estimated Timeline

| Phase | Days | Notes |
|-------|------|-------|
| Setup | 0.5 | Fastest part |
| Data Ingestion | 1 | Depends on document format |
| Tools | 1.5 | Core complexity |
| Orchestrator | 1 | Most complex piece |
| API | 0.5 | Boilerplate |
| UI | 1 | Streamlit is fast |
| Optional Features | 1 | If time permits |
| Demo + Submission | 0.5 | |
| **Total** | **7 days** | |

---

## Risk Flags

| Risk | Mitigation |
|------|-----------|
| Documents provided in bad formats | Request originals; write robust parsers for PDF, docx, txt |
| Excel schema is unclear | Write `print_schema.py` utility to inspect structure |
| LLM hallucinates outside provided docs | Strict system prompt: "If you cannot find the answer in your tools, say so." |
| Confirmation gate broken = accidental actions | Unit test the confirmation gate with an integration test before recording demo |
| Cross-account leakage | Write explicit test cases that attempt cross-account queries |
