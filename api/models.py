from pydantic import BaseModel
from typing import Any


class LoginRequest(BaseModel):
    account_id: str  # e.g. "ACC-001" or "INTERNAL"


class LoginResponse(BaseModel):
    session_id: str
    account_id: str
    company_name: str
    role: str  # "customer" | "internal"


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ToolCallSummary(BaseModel):
    name: str
    inputs: dict
    output: dict


class ChatResponse(BaseModel):
    text: str
    tool_calls: list[ToolCallSummary]
    pending_action: dict | None = None
    session_id: str


class ConfirmRequest(BaseModel):
    session_id: str
    action_id: str
    confirmed: bool


class ConfirmResponse(BaseModel):
    text: str
    tool_calls: list[ToolCallSummary]
    session_id: str
