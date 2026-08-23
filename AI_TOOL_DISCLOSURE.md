# AI Tool Usage Disclosure

This document lists all AI tools used in the development and runtime of the ParcelPilot AI
Support System, as required by the CalQuity assessment guidelines.

---

## Runtime AI — Production LLM

### Groq API (OpenAI-compatible endpoint)
- **Model used in the product**: `openai/gpt-oss-120b` (configurable via `GROQ_MODEL` env var)
- **Role**: Powers the agent's reasoning, tool selection, and response generation at runtime
- **API**: OpenAI-compatible Python SDK (`openai` package) pointed at `https://api.groq.com/openai/v1`
- **Tool calling**: OpenAI tool_use format (`tools=` parameter in `chat.completions.create`)
- **Key**: `GROQ_API_KEY` in `.env` (gitignored; never committed)

---

## Development AI — Pair Programming

### Claude Code (Anthropic)
- **Version**: Claude Sonnet 4.6 (`claude-sonnet-4-6`)
- **Role**: Used as an AI pair-programming assistant throughout development
- **Tasks assisted with**:
  - Architecting the ReAct agent tool design and confirmation gate pattern
  - Writing and reviewing Python code across all modules
  - Drafting HLD/LLD/ARCHITECTURE documentation
  - Designing the system prompt for the orchestrator
  - Writing integration tests for access control and trust hierarchy
  - Implementing reliability safeguards (graceful error handling, test isolation)
  - Phase-by-phase implementation and verification assistance

---

## Embeddings — Local (No External API)

### SentenceTransformers
- **Model**: `all-MiniLM-L6-v2` (via `sentence-transformers` library)
- **Role**: Generates 384-dimensional embeddings for document chunks stored in ChromaDB
- **Note**: Runs locally — no external API call or additional key required

---

## What Was NOT AI-Generated

- All design decisions (authority weight formula, two-phase confirmation gate,
  tool-layer access control) were reasoned through by the developer
- Test cases for access control edge cases (cross-account blocking, deprecated doc
  trust ranking) were designed by the developer
- The source trust hierarchy and conflict detection logic reflect deliberate
  engineering choices about system behaviour under uncertainty
- The real assessment data (Excel workbook + PDFs) are used as-is; no AI-generated
  synthetic data is used in the production system

---

## Transparency Note

The use of AI tools in development is consistent with modern engineering practice
and is explicitly encouraged by the assessment guidelines. The final system is
evaluated on its architecture, correctness, and design decisions — all of which
reflect the developer's judgment and understanding.
