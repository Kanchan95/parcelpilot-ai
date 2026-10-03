# Product Note — ParcelPilot AI Support System

---

## Which Additional Client Problem We Chose (and Why Both)

We addressed **both** optional problems — Proactive Issue Detection and Trust &
Reliability — because they are not independent. Proactive detection without trust
handling is dangerous: the system might confidently surface a false pattern based on
an incorrect historical resolution. Trust handling without proactive detection is
incomplete: you only get reliability when someone happens to ask a question.
Together, they form a complete picture of a system that is both safe and useful.

**Proactive Issue Detection** (implemented in `agent/analysis/issue_detector.py`):
- Complaint cluster detection: groups tickets by `issue_type` over a rolling 30-day
  window, flags types with ≥3 occurrences (e.g., 5 billing disputes this month).
- SLA breach surfacing: all open tickets with `sla_breach = 1`, grouped by account
  and sorted by priority.
- Overdue order detection: `in_transit` orders past their `estimated_delivery` date,
  relative to the dataset snapshot time (not `datetime.now()`).
- Stale resolution flagging: resolved tickets whose resolution text references
  deprecated policy versions — these may have given customers incorrect information
  (e.g., a 14-day refund window that was later extended to 30 days).

**Trust & Reliability** (built into every layer):
- Each document chunk carries a numeric `authority_level` (15–100) and an
  `is_deprecated` boolean stored as ChromaDB metadata.
- Retrieval re-ranks by `cosine_similarity × authority_weight`, ensuring that a
  slightly less relevant customer agreement beats a highly relevant deprecated policy.
- When chunks from different authority tiers appear together in the top-K results,
  conflict detection fires and the agent is instructed to surface both sources
  explicitly with a statement of which it is trusting and why.
- Historical ticket resolutions are stored in SQLite only (not in the vector store)
  and are always accompanied by a disclaimer: they may contain incorrect information
  and should be treated as context only.

---

## What Else We Would Build for ParcelPilot

Prioritised by expected business impact:

### Priority 1 — Policy Change Detection
**Why it matters most**: The biggest source of incorrect AI answers is stale policy
in the vector store. When a policy document is updated, the current system continues
citing the old version until an operator manually re-ingests it. A file-watcher or
webhook that triggers automatic re-ingestion on document upload — and diffs the new
chunks against the old to flag changes — would prevent the single most dangerous
failure mode: confident answers based on superseded policy.

**Implementation**: A background job that hashes each document on ingest, detects
changes on next run, re-ingests changed documents, and writes a "policy changed"
event to the ops team's digest.

### Priority 2 — Self-Service Credit and Cancellation Portal
**Why it matters**: Data analysis of the mock dataset suggests that SLA breach
credits, billing dispute refunds, and straightforward cancellations follow deterministic
eligibility rules. These account for an estimated 40–60% of ticket volume. A
self-service flow that lets customers check eligibility, see the exact credit amount
or cancellation fee, and approve the action — without agent involvement — is where
the majority of ticket deflection comes from.

**Implementation**: Extend the confirmation gate to support a customer-initiated
flow: check eligibility → show outcome → confirm → execute → auto-close ticket.

### Priority 3 — Resolution Feedback Loop
**Why it matters**: The system will make mistakes, especially early. Without a
feedback mechanism, errors compound silently. An ops agent reviewing an AI response
should be able to flag it as incorrect with one click. Those flags feed into the
retrieval ranking as negative signals for that chunk — the system learns what NOT
to cite for which query types.

**Implementation**: Add a `chunk_feedback` table. On flag, decrement the chunk's
retrieval weight. After N flags, quarantine the chunk and alert an admin.

---

## What We Intentionally Left Out

1. **Real authentication and session management**: The demo uses a dropdown to select
   `account_id`. A production system needs OAuth 2.0 / SSO, JWT with expiry, MFA
   for internal agents, and a persistent session store (Redis). Omitted because it
   adds infrastructure complexity without testing the AI system design, which is the
   focus of this project.

2. **Live carrier API integration**: Answering "where is my package right now?"
   requires live tracking data from carrier APIs (e.g., Delhivery, Blue Dart, FedEx).
   The data pack contains order records with `tracking_number` fields but no live feed.
   Omitted because it is out of scope for the supplied data.

3. **Scheduled proactive reporting**: The issue detector runs on-demand. A production
   system would run it on a schedule (e.g., daily at 8 AM) and push a digest to Slack
   or email. Omitted because scheduling infrastructure is not the core focus of this project.

4. **Multi-language support**: ParcelPilot likely serves customers in multiple Indian
   languages. Claude handles multilingual queries natively, but the source documents
   are English-only. Translation of source documents is a significant effort left for
   a production roadmap.

5. **Fine-tuned routing classifier**: At high ticket volume, sending every query
   through the full Claude ReAct loop is expensive. A fast classifier (e.g., a small
   fine-tuned model) that identifies simple queries (order status, balance check) and
   handles them with a direct DB lookup — bypassing the LLM entirely — would cut
   latency and cost by 60–70%. Not worth the complexity for a corpus of
   12 tickets and 10 orders.

---

## One Metric to Judge Whether This Product Is Useful

**Ticket deflection rate**: the percentage of support requests fully resolved by
the AI (including any required actions) without human escalation, measured weekly.

**Definition**: `tickets_resolved_by_ai / tickets_opened` where `resolved_by_ai`
means status = 'resolved' and the final action was performed by or confirmed through
the AI system, with no subsequent reopening or human edit within 48 hours.

**Why this metric and not others**:

- *Response time* measures speed, not quality. A fast wrong answer is worse than
  a slow correct one, especially when actions (cancellations, credits) are involved.
- *CSAT score* is a lagging, opt-in metric that under-samples and rewards pleasant
  responses over accurate ones.
- *Accuracy* requires ground-truth labels for every query at scale — expensive to
  produce and maintain.
- *Deflection rate* maps directly to the stated business problem: "20-person ops team
  manually processes hundreds of weekly support requests." If the number of tickets
  the team needs to personally touch drops by 50%, the product is working. If it
  doesn't, it isn't — regardless of how fast or pleasant the AI responses are.

**Target**: ≥50% deflection by week 4 of deployment, with a weekly upward trend
as the system is refined based on flagged resolutions and policy updates.

**How to instrument**: Tag every ticket at creation. When status transitions to
'resolved', record: `resolved_by` (agent_id or 'ai'), `resolution_method`
('ai_direct' | 'ai_with_confirmation' | 'human' | 'ai_escalated_to_human').
Report weekly.
