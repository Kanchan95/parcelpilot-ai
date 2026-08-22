"""
ParcelPilot AI — FastAPI server
Run: python server.py
"""
import sys
import json
import uuid
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

import config
from agent.orchestrator import Orchestrator

app = FastAPI(title="ParcelPilot AI", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory sessions (fine for demo)
SESSIONS: dict[str, dict] = {}


def _session(session_id: str) -> dict:
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(401, "Session expired. Please log in again.")
    return s


def _get_plan(account_id: str) -> str:
    try:
        conn = sqlite3.connect(config.DB_PATH)
        row = conn.execute(
            "SELECT plan FROM accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else "Standard"
    except Exception:
        return "Standard"


# ── Routes ───────────────────────────────────────────────────────────────────

_DIST = Path(__file__).parent / "web" / "dist"

# Serve React build in production (after `npm run build` inside web/)
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    async def root():
        return FileResponse(_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        file = _DIST / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return FileResponse("frontend/index.html")


@app.get("/api/accounts")
async def list_accounts():
    return {"accounts": [
        {"id": k, "company": v["company"], "role": v["role"]}
        for k, v in config.DEMO_ACCOUNTS.items()
    ]}


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    account_id = (body.get("account_id") or "").strip()

    if account_id not in config.DEMO_ACCOUNTS:
        raise HTTPException(400, f"Unknown account: {account_id}")

    info = config.DEMO_ACCOUNTS[account_id]
    is_internal = info["role"] == "internal"
    plan = "internal" if is_internal else _get_plan(account_id)
    sid = str(uuid.uuid4())

    orch = Orchestrator(account_id=account_id, is_internal=is_internal, session_id=sid)
    SESSIONS[sid] = {
        "orchestrator": orch,
        "account_id": account_id,
        "company": info["company"],
        "plan": plan,
        "is_internal": is_internal,
    }

    return {
        "session_id": sid,
        "account_id": account_id,
        "company": info["company"],
        "plan": plan,
        "is_internal": is_internal,
        "snapshot": config.get_snapshot_time(),
    }


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    session = _session(body.get("session_id", ""))
    orch: Orchestrator = session["orchestrator"]

    response = orch.chat(body.get("message", "").strip())

    return {
        "text": response.text,
        "tool_calls": [
            {"name": tc.name, "inputs": tc.inputs, "output": tc.output}
            for tc in response.tool_calls
        ],
        "pending_action": response.pending_action,
    }


@app.post("/api/confirm")
async def confirm(request: Request):
    body = await request.json()
    session = _session(body.get("session_id", ""))
    orch: Orchestrator = session["orchestrator"]

    response = orch.notify_confirmation(
        action_id=body["action_id"],
        confirmed=body.get("confirmed", False),
    )

    return {
        "text": response.text,
        "tool_calls": [
            {"name": tc.name, "inputs": tc.inputs, "output": tc.output}
            for tc in response.tool_calls
        ],
        "pending_action": response.pending_action,
    }


@app.get("/api/stats")
async def stats(session_id: str):
    session = _session(session_id)
    if not session["is_internal"]:
        return {}
    try:
        conn = sqlite3.connect(config.DB_PATH)
        r = lambda q: conn.execute(q).fetchone()[0]
        data = {
            "open_tickets":    r("SELECT COUNT(*) FROM tickets WHERE LOWER(status) NOT IN ('closed','resolved')"),
            "pending_cancels": r("SELECT COUNT(*) FROM orders WHERE cancellation_requested_at IS NOT NULL AND UPPER(status) IN ('BOOKED','PICKED_UP')"),
            "missed_pickups":  r("SELECT COUNT(*) FROM orders WHERE UPPER(status)='BOOKED' AND pickup_window_end < '2026-08-16 11:00' AND pickup_actual_at IS NULL"),
            "accounts":        r("SELECT COUNT(*) FROM accounts"),
        }
        conn.close()
        return data
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/logout")
async def logout(request: Request):
    body = await request.json()
    SESSIONS.pop(body.get("session_id", ""), None)
    return {"ok": True}


if __name__ == "__main__":
    print("\n  ParcelPilot AI  →  http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
