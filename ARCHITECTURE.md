# Architecture Note — ParcelPilot AI Support System

---

## Agent Design

The system uses a **ReAct (Reason + Act) loop** with the LLM's tool_use API
(OpenAI-compatible format, served via Groq) rather than a single-pass RAG pipeline.

**Why ReAct and not simple RAG?**
The two example queries from the assessment reveal why:

> "Can Northstar cancel ORD-1001 without a cancellation fee?"

Answering this correctly requires four sequential operations:
1. Look up ORD-1001 in the database to get its creation time and status.
2. Search documents for Northstar's specific cancellation terms (their agreement may
   differ from the general policy).
3. Calculate whether the order's age (relative to the dataset snapshot time) falls
   within Northstar's free-cancellation window.
4. Give a definitive YES/NO with the chain of reasoning.

No single retrieval step can do this. The agent must reason, retrieve, observe,
reason again, retrieve again, then synthesise a conclusion. ReAct makes this
explicit and auditable — each tool call and its result is logged and shown in the UI.

**How the loop works:**
```
User message → append to history
While iterations < 10:
    response = client.chat.completions.create(tools=..., messages=history)
    If finish_reason == "stop": return final text
    If finish_reason == "tool_calls":
        For each tool_call:
            Execute the tool (with session-scoped access control)
            Append tool_result to history
        Continue loop
```

**The 10-iteration guard** prevents runaway loops. If hit, the agent surfaces a
graceful error asking the user to rephrase.

**One Orchestrator, two personas:**
Rather than separate customer-facing and internal agents, a single orchestrator handles
both. The session's `is_internal` flag changes what the tools return: customers see
only their own data; internal agents see all accounts. The system prompt is identical
for both — the data layer enforces the access boundary, not the LLM.

---

## Tool Design

Three tools are separated by concern, not by convenience.

### Tool A — Document Search (RAG)
**Concern**: What do policies, agreements, and SOPs say about a topic?

**Flow**:
1. Embed the user's query using `all-MiniLM-L6-v2` (384 dimensions).
2. Query ChromaDB with a metadata filter scoped to: (a) globally-applicable documents
   AND (b) the customer's specific agreement (by `account_scope`).
3. Re-rank the top-12 results by `cosine_similarity × authority_weight`.
4. Return the top-5 chunks with full source attribution.
5. Run conflict detection over the top-5: if current and deprecated chunks appear
   together, or a customer agreement contradicts a general policy, emit a conflict record.

The tool never silently picks a winner. It returns the conflict to the LLM, which
is instructed to surface both sources and state which it is following.

**Authority weights used in re-ranking:**
| Source type | Weight |
|-------------|--------|
| customer_agreement | 3.0× |
| current_policy | 2.0× |
| current_sop / product_guide | 1.6–1.8× |
| deprecated_policy | 0.4× |
| deprecated_sop | 0.3× |

A slightly less relevant customer agreement chunk will always beat a highly relevant
deprecated policy chunk. This is the correct behaviour for "agreement overrides policy."

### Tool B — Structured Data Lookup
**Concern**: What is factually true about this account, order, or ticket right now?

**Operations**: `get_account_info`, `get_order`, `list_orders`, `get_ticket`,
`list_tickets`, `get_credit_balance`, `sla_breach_report`, `proactive_report`.

**Access control**: Every SQL query that touches account-scoped data appends
`AND account_id = :session_account_id`. This is hardcoded in the tool — the LLM
never supplies `account_id` as a tool parameter, so prompt injection cannot change
which account's data is returned.

**Snapshot time**: All time-based comparisons use the reference time from the
workbook's README sheet (stored in `.snapshot_time` on first ingestion), not
`datetime.now()`. This ensures consistent answers regardless of when the demo runs.

### Tool C — Action Executor (Two-Phase Confirmation Gate)
**Concern**: What state changes need to happen, and did the user authorise them?

**Phase 1** — `request_action()`:
The LLM calls `execute_action(action_type, parameters)`. The tool generates a UUID
`action_id`, stores the pending action in memory, and returns:
```json
{
  "status": "requires_confirmation",
  "action_id": "...",
  "summary": "Cancel order ORD-1001 (free cancellation per Northstar agreement)."
}
```
The LLM receives this response and is instructed to relay the summary to the user
and ask for explicit confirmation. The action is NOT executed.

**Phase 2** — `confirm_action(action_id)`:
The user clicks Confirm in the UI. The UI calls `confirm_action(action_id)` directly
(not through the LLM). The tool pops the pending action from memory, executes the
database mutation, writes to `actions_log`, and returns the result. The result is
then injected into the conversation so Claude can write a closing response.

**Why this design matters**: The LLM cannot trigger execution. Only the user's
explicit UI action (clicking Confirm) does. This prevents the single worst failure
mode: an LLM confidently executing an irreversible action it misunderstood.

---

## Document and Structured-Data Handling

**Document ingestion**:
- Supports `.pdf` (via `pdfplumber`) and `.txt`.
- Chunks at 500 words with 80-word overlap — sized to fit meaningful policy
  paragraphs without losing cross-sentence context.
- Minimum chunk length of 10 words filters out headers and page numbers.
- Each chunk is tagged: `source_type`, `authority_level`, `is_deprecated`,
  `account_scope` (global vs. specific account name), `chunk_index`.

**Structured data ingestion**:
- Excel workbook → SQLite via pandas.
- The README sheet's snapshot time is extracted on ingest and stored in
  `.snapshot_time` for use by the agent at runtime.
- Historical ticket resolutions are loaded to SQLite but **never embedded**
  into the vector store. They are always returned with a disclaimer that they
  may contain incorrect information.

---

## Source Reliability and Conflict Handling

**Three types of source conflicts we handle:**

1. **Version conflict** (current vs. deprecated):
   When the top-K results include chunks from both a current and a deprecated
   version of the same policy, the conflict detector fires and emits:
   ```
   {type: "version_conflict", trusted: "Support Policy v3", deprecated: "Support Policy v2"}
   ```
   The agent says: "I found two versions of this policy. The current policy says X.
   A deprecated version says Y. I'm following the current policy."

2. **Agreement override** (customer agreement vs. general policy):
   When a customer's specific agreement appears alongside a general policy on the
   same topic, the agent is instructed to say: "Your agreement with ParcelPilot
   gives you different terms. The standard policy says X, but your agreement says Y.
   Your agreement takes precedence."

3. **Data vs. document conflict**:
   If structured data (e.g., an order's actual status) contradicts what a document
   predicts (e.g., "orders in transit cannot be cancelled"), the structured data wins.
   The agent is instructed: "Structured account/order data reflects the ground truth.
   Policy documents describe the rules, not the current state."

**Historical ticket resolutions**:
These are never indexed for retrieval. They are only accessible via `lookup_data` and
are always prefaced with: "Note: this is a historical resolution that may not reflect
current policy." This is the most dangerous source of silent errors in a naive system.

**Uncertainty disclosure**:
When the agent must cite a deprecated source (because no current content matches),
it says so. When it cannot find relevant information at all, it says so and offers
to create an escalation rather than hallucinating.

---

## Major Technical Trade-offs

### 1. Local embeddings vs. API embeddings
**Chosen**: `sentence-transformers/all-MiniLM-L6-v2` (local, 384-dim)
**Trade-off**: No second API key, zero latency for embedding queries, runs offline.
Cost: smaller model than OpenAI `text-embedding-3-large` (1536-dim), may miss
fine-grained semantic distinctions in longer policy paragraphs.
**Production flip point**: If the document corpus grows beyond ~100 documents or
precision on policy-specific queries degrades, switch to OpenAI or Voyage AI embeddings.

### 2. SQLite vs. PostgreSQL
**Chosen**: SQLite (built-in Python, no server)
**Trade-off**: Single-file, zero setup, fully portable. Ideal for an assessment demo
that must run in one command on any machine.
Cost: no concurrent writes, no row-level security, limited to a single process.
**Production flip point**: The first time two concurrent agents need to write to the
DB simultaneously, or when proper RLS per account_id is needed — switch to Postgres.

### 3. Single agent vs. multi-agent architecture
**Chosen**: Single orchestrator, two personas controlled by `is_internal` flag.
**Trade-off**: Simpler debugging, single message history, one API connection per session.
Cost: the system prompt and tool set are shared, so internal-only tools (proactive_report)
are technically callable by any session — the `is_internal` check at the tool layer
enforces the boundary, but a separate agent would be cleaner.
**Production flip point**: When the internal agent needs substantially different tools
(e.g., bulk operations, carrier API access) that would bloat the customer agent's
context, split into two separate agent configs.

### 4. In-memory session store vs. Redis
**Chosen**: Python dict keyed by session UUID.
**Trade-off**: Zero infrastructure. Works perfectly for a single-server demo.
Cost: sessions lost on server restart; cannot scale horizontally.
**Production flip point**: The first deployment with more than one server instance.

### 5. ReAct loop vs. LangGraph / LangChain
**Chosen**: OpenAI-compatible SDK with Groq endpoint (no framework abstractions)
**Trade-off**: Full control over every aspect of the loop: iteration count, tool
dispatch, confirmation gate, message history format. No hidden abstractions.
Cost: more code to write and maintain; no built-in streaming, memory management,
or graph visualisation.
**Rationale**: For a high-trust system where wrong behaviour has consequences,
understanding exactly what happens at each step is more important than framework
convenience. The overhead is low for a focused 3-tool agent.
