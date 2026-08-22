"""
Orchestrator — ReAct agent loop using OpenAI's function-calling API.

OpenAI uses "tools" with "type: function" format (different from Anthropic's tool_use).
The logic is the same: reason → call tool → observe result → reason again → repeat.

Key design principles:
  - account_id comes from the trusted session, never from the LLM's tool inputs.
  - Confirmation gate: action_executor returns "requires_confirmation" on first call;
    the loop pauses and surfaces this to the caller (UI).
  - Max iteration guard prevents infinite loops.
  - All API errors are caught and returned as user-friendly AgentResponse messages;
    raw provider errors never propagate to the HTTP layer.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any
import openai

logger = logging.getLogger(__name__)

import config
from agent.tools import document_search, structured_lookup, action_executor

MAX_ITERATIONS = 10


def _build_system_prompt() -> str:
    snapshot_time = config.get_snapshot_time()
    return f"""You are ParcelPilot AI — an intelligent support assistant for ParcelPilot's
logistics platform. You help both customers (who can only access their own data) and
internal operations agents.

## IMPORTANT: Dataset Reference Time
The current reference time for this dataset is: **{snapshot_time}**
ALL time-based reasoning (cancellation windows, SLA deadlines, order ages, "hours late",
"days ago") must be calculated relative to this reference time — NOT relative to today's
actual date. For example, if an order was created at 09:00 and the reference time is 11:00,
it has been 2 hours since creation.

## Available Tools

1. **search_documents** — Search policy documents, SOPs, and customer-specific agreements.
   Use for: refund windows, cancellation policies, SLA terms, procedures, entitlements.

2. **lookup_data** — Query account details, order status, and support tickets from the database.
   Use for: order status, credit balance, ticket history, account plan details.

3. **execute_action** — Request a state-changing action (cancel order, apply credit, update ticket).
   IMPORTANT: This ALWAYS returns a confirmation request first — the action does NOT execute
   until the user explicitly confirms. You MUST present the confirmation summary to the user
   and tell them to click Confirm or Cancel.

## Source Trust Hierarchy — FOLLOW THIS STRICTLY
When sources conflict, trust them in this order (highest first):
  1. Customer-specific service agreements (highest — always override general policy)
  2. Current official policy documents
  3. Current SOPs
  4. Deprecated policy / SOP documents (outdated — cite only if nothing current exists)

## Rules You MUST Follow

### Accuracy
- ONLY answer using information from your tools. Never use general knowledge for policy facts.
- Always name the source you are drawing from.
- If you cannot find information, say so clearly.

### Source Conflicts
- If you retrieve both a current and deprecated source: "I found conflicting versions. The
  current policy says X. A deprecated version says Y. I am following the current policy."
- If a customer agreement overrides general policy: "Your agreement gives you different terms
  than the standard policy. Your agreement takes precedence."

### Actions
- NEVER claim an action was completed before the user confirms. Always relay the confirmation
  summary and instruct the user to confirm.

### YES/NO Answers
- For yes/no decisions (eligibility for credit, cancellation fee, etc.) give YES or NO first,
  then show your step-by-step reasoning including the time calculation.
- Show your working: "Booked at [time]. Reference time is [snapshot]. That is X hours ago.
  Policy says Y. Therefore: YES/NO."

### Escalation
- If a request is outside policy or requires human judgment, offer to create an escalation ticket.

## Response Style
- Concise, clear, professional.
- YES/NO decisions first, reasoning second.
- Use bullet points for multi-part answers."""


# ── Tool definitions in OpenAI function-calling format ───────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Search the policy documents, SOPs, and customer agreements for information "
                "about cancellation policies, SLA terms, refund windows, credit rules, "
                "procedures, and account entitlements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_data",
            "description": (
                "Query the database for structured data: account information, order status, "
                "ticket details, credit balance, SLA breach reports, or proactive issue digest."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "get_account_info",
                            "get_order",
                            "list_orders",
                            "get_ticket",
                            "list_tickets",
                            "get_credit_balance",
                            "sla_breach_report",
                            "proactive_report",
                        ],
                        "description": (
                            "The data operation to perform. "
                            "Use 'proactive_report' (internal only) for a full issue digest."
                        ),
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Operation-specific parameters. Examples: "
                            "{'order_id': 'ORD-1001'}, "
                            "{'ticket_id': 'TKT-501'}, "
                            "{'status': 'open'}."
                        ),
                    },
                },
                "required": ["operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_action",
            "description": (
                "Request a state-changing action. Returns a confirmation request — the action "
                "is NOT executed until the user confirms. Always present the confirmation "
                "summary to the user before proceeding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": [
                            "cancel_order",
                            "apply_credit",
                            "update_ticket_status",
                            "escalate_ticket",
                            "close_ticket",
                            "create_escalation",
                        ],
                        "description": "The type of action to perform.",
                    },
                    "parameters": {
                        "type": "object",
                        "description": (
                            "Action parameters. Examples: "
                            "cancel_order: {'order_id': 'ORD-1001'}; "
                            "apply_credit: {'amount': 300, 'reason': 'SLA breach'}; "
                            "update_ticket_status: {'ticket_id': 'TKT-501', 'new_status': 'in_progress'}; "
                            "close_ticket: {'ticket_id': 'TKT-503', 'resolution': 'Billing contact updated.'}; "
                            "create_escalation: {'reason': 'API key exposure P1', 'priority': 'critical'}."
                        ),
                    },
                },
                "required": ["action_type", "parameters"],
            },
        },
    },
]


@dataclass
class ToolCall:
    name: str
    tool_use_id: str
    inputs: dict
    output: dict


@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    pending_action: dict | None = None


class Orchestrator:
    """
    One instance per conversation session.
    Maintains message history (without system prompt — that is injected fresh each call).
    """

    def __init__(self, account_id: str, is_internal: bool, session_id: str):
        self.account_id = account_id
        self.is_internal = is_internal
        self.session_id = session_id
        self.messages: list[dict] = []   # history WITHOUT the system message
        self._config_error: str | None = None

        # Auto-select provider: Groq → OpenAI → deferred error
        # We defer the error so login succeeds and the first chat message returns
        # a clean user-facing message instead of a server-level 500.
        if config.GROQ_API_KEY:
            self.client: openai.OpenAI | None = openai.OpenAI(
                api_key=config.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
            )
            self.model = config.GROQ_MODEL
        elif config.OPENAI_API_KEY:
            self.client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
            self.model = config.OPENAI_MODEL
        else:
            self.client = None
            self.model = ""
            self._config_error = (
                "No AI provider API key is configured. "
                "Set GROQ_API_KEY or OPENAI_API_KEY in .env and restart the server."
            )
            logger.error("Orchestrator created with no API key — AI calls will fail gracefully.")

    def chat(self, user_message: str) -> AgentResponse:
        """Process one user turn and return the agent response."""
        # Fail gracefully if no API key was available at startup.
        if self.client is None:
            return AgentResponse(
                text=(
                    "⚠️ The AI service is not configured. "
                    "Please contact your administrator."
                ),
                tool_calls=[],
                pending_action=None,
            )

        if user_message:
            self.messages.append({"role": "user", "content": user_message})

        tool_calls_log: list[ToolCall] = []
        pending_action: dict | None = None

        for _ in range(MAX_ITERATIONS):
            # System prompt injected fresh every call (snapshot time may change)
            full_messages = [
                {"role": "system", "content": _build_system_prompt()}
            ] + self.messages

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=config.MAX_TOKENS,
                    messages=full_messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )
            except openai.RateLimitError:
                logger.warning("Groq/OpenAI rate limit hit (429).")
                return AgentResponse(
                    text=(
                        "⚠️ The AI service is temporarily rate-limited. "
                        "Please wait a moment and try again."
                    ),
                    tool_calls=tool_calls_log,
                    pending_action=pending_action,
                )
            except openai.AuthenticationError:
                logger.error("AI provider authentication failed — check API key.")
                return AgentResponse(
                    text=(
                        "⚠️ The AI service could not be authenticated. "
                        "Please contact your administrator."
                    ),
                    tool_calls=tool_calls_log,
                    pending_action=pending_action,
                )
            except (openai.APIConnectionError, openai.APITimeoutError) as exc:
                logger.warning("AI provider connection/timeout error: %s", exc)
                return AgentResponse(
                    text=(
                        "⚠️ Could not reach the AI service. "
                        "Please check your connection and try again."
                    ),
                    tool_calls=tool_calls_log,
                    pending_action=pending_action,
                )
            except openai.APIStatusError as exc:
                logger.error("AI provider API error %s: %s", exc.status_code, exc.message)
                return AgentResponse(
                    text=(
                        "⚠️ The AI service returned an unexpected error. "
                        "Please try again shortly."
                    ),
                    tool_calls=tool_calls_log,
                    pending_action=pending_action,
                )
            except openai.OpenAIError as exc:
                logger.error("Unexpected OpenAI SDK error: %s", exc)
                return AgentResponse(
                    text=(
                        "⚠️ An unexpected AI service error occurred. "
                        "Please try again shortly."
                    ),
                    tool_calls=tool_calls_log,
                    pending_action=pending_action,
                )

            choice = response.choices[0]
            msg = choice.message

            # Append assistant turn to history
            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            self.messages.append(assistant_entry)

            # Done — no more tool calls
            if choice.finish_reason == "stop":
                return AgentResponse(
                    text=msg.content or "",
                    tool_calls=tool_calls_log,
                    pending_action=pending_action,
                )

            # Tool calls requested
            if choice.finish_reason == "tool_calls" and msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        inputs = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        # Malformed arguments from LLM — feed error back so it can recover
                        logger.warning("Malformed tool arguments for %s: %s", tc.function.name, tc.function.arguments)
                        inputs = {}
                        raw_output: dict = {"error": "Malformed tool arguments — could not parse JSON."}
                        tool_calls_log.append(ToolCall(
                            name=tc.function.name,
                            tool_use_id=tc.id,
                            inputs=inputs,
                            output=raw_output,
                        ))
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(raw_output),
                        })
                        continue

                    raw_output = self._dispatch_tool(tc.function.name, inputs)

                    tool_calls_log.append(ToolCall(
                        name=tc.function.name,
                        tool_use_id=tc.id,
                        inputs=inputs,
                        output=raw_output,
                    ))

                    if raw_output.get("status") == "requires_confirmation":
                        pending_action = raw_output

                    # Feed result back into history
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(raw_output),
                    })
                continue

            break  # unexpected finish_reason

        return AgentResponse(
            text="I reached the maximum number of reasoning steps. Please try rephrasing.",
            tool_calls=tool_calls_log,
            pending_action=pending_action,
        )

    def notify_confirmation(self, action_id: str, confirmed: bool) -> AgentResponse:
        """
        Called after the user confirms or cancels a pending action.
        Injects the result so the LLM can write a closing response.
        """
        if confirmed:
            result = action_executor.confirm_action(action_id)
            content = f"The user confirmed the action. Execution result: {json.dumps(result)}"
        else:
            action_executor.cancel_pending_action(action_id)
            content = "The user cancelled the action. No changes were made."

        self.messages.append({"role": "user", "content": content})
        return self.chat("")

    def reset(self) -> None:
        self.messages.clear()

    # ── Private helpers ──────────────────────────────────────────────────────

    def _dispatch_tool(self, name: str, inputs: dict) -> dict:
        if name == "search_documents":
            return document_search.search(
                query=inputs["query"],
                account_id=self.account_id,
            )

        if name == "lookup_data":
            return structured_lookup.lookup(
                operation=inputs["operation"],
                params=inputs.get("params", {}),
                session_account_id=self.account_id,
                is_internal=self.is_internal,
            )

        if name == "execute_action":
            return action_executor.request_action(
                action_type=inputs["action_type"],
                parameters=inputs["parameters"],
                session_account_id=self.account_id,
                session_id=self.session_id,
                is_internal=self.is_internal,
            )

        return {"error": f"Unknown tool: {name}"}
