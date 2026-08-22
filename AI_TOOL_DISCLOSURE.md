# AI Tool Usage Disclosure

This document lists all AI tools used in the development of the ParcelPilot AI
Support System, as required by the CalQuity assessment guidelines.

---

## Tools Used

### 1. Claude (Anthropic) — Primary LLM
- **Model used in the product**: `claude-sonnet-4-6` via the Anthropic Python SDK
- **Role**: Powers the agent's reasoning, tool selection, and response generation
- **API**: Anthropic Messages API with native `tool_use` (not LangChain)

### 2. Claude Code (Anthropic) — Development Assistant
- **Version**: Claude Sonnet 4.6 (claude-sonnet-4-6)
- **Role**: Used as an AI pair-programming assistant during development
- **Tasks assisted with**:
  - Architecting the agent tool design and confirmation gate pattern
  - Writing and reviewing Python code across all modules
  - Drafting the HLD/LLD documentation
  - Generating realistic mock data (documents and Excel data)
  - Designing the system prompt for the orchestrator
  - Writing integration tests for access control and trust hierarchy

### 3. SentenceTransformers — Embedding Model
- **Model**: `all-MiniLM-L6-v2` (via `sentence-transformers` library)
- **Role**: Generates 384-dimensional embeddings for document chunks
- **Note**: Runs locally — no external API call required

---

## What Was NOT AI-Generated

- All design decisions (authority weight formula, two-phase confirmation gate,
  tool-layer access control) were reasoned through by the developer
- Test cases for access control edge cases (cross-account blocking, deprecated doc
  trust ranking) were designed by the developer
- The source trust hierarchy and conflict detection logic reflect deliberate
  engineering choices about system behaviour under uncertainty

---

## Transparency Note

The use of AI tools in development is consistent with modern engineering practice
and is explicitly encouraged by the assessment guidelines. The final system is
evaluated on its architecture, correctness, and design decisions — all of which
reflect the developer's judgment and understanding.
