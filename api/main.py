"""
FastAPI backend for ParcelPilot AI.

Endpoints:
  POST /api/auth/login   — exchange account_id for a session
  POST /api/chat         — send a message, get agent response
  POST /api/confirm      — confirm or cancel a pending action
  GET  /api/health       — liveness probe
"""

import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from api.models import (
    LoginRequest, LoginResponse,
    ChatRequest, ChatResponse,
    ConfirmRequest, ConfirmResponse,
    ToolCallSummary,
)
from agent.orchestrator import Orchestrator

app = FastAPI(title="ParcelPilot AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# session_id → Orchestrator instance
_sessions: dict[str, Orchestrator] = {}


def _get_session(session_id: str) -> Orchestrator:
    orch = _sessions.get(session_id)
    if orch is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")
    return orch


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": config.CLAUDE_MODEL}


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    account_info = config.DEMO_ACCOUNTS.get(req.account_id)
    if account_info is None:
        raise HTTPException(
            status_code=401,
            detail=f"Unknown account_id '{req.account_id}'. Valid IDs: {list(config.DEMO_ACCOUNTS.keys())}",
        )

    session_id = str(uuid.uuid4())
    is_internal = account_info["role"] == "internal"
    _sessions[session_id] = Orchestrator(
        account_id=req.account_id,
        is_internal=is_internal,
        session_id=session_id,
    )

    return LoginResponse(
        session_id=session_id,
        account_id=req.account_id,
        company_name=account_info["company"],
        role=account_info["role"],
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    orch = _get_session(req.session_id)
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    response = orch.chat(req.message)

    return ChatResponse(
        text=response.text,
        tool_calls=[
            ToolCallSummary(name=tc.name, inputs=tc.inputs, output=tc.output)
            for tc in response.tool_calls
        ],
        pending_action=response.pending_action,
        session_id=req.session_id,
    )


@app.post("/api/confirm", response_model=ConfirmResponse)
async def confirm(req: ConfirmRequest):
    orch = _get_session(req.session_id)
    response = orch.notify_confirmation(req.action_id, req.confirmed)

    return ConfirmResponse(
        text=response.text,
        tool_calls=[
            ToolCallSummary(name=tc.name, inputs=tc.inputs, output=tc.output)
            for tc in response.tool_calls
        ],
        session_id=req.session_id,
    )


@app.delete("/api/session/{session_id}")
async def logout(session_id: str):
    _sessions.pop(session_id, None)
    return {"status": "logged out"}
