"""
ParcelPilot AI — Streamlit UI
Run: streamlit run ui/app.py
"""
import sys, uuid, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import config
from agent.orchestrator import Orchestrator

st.set_page_config(
    page_title="ParcelPilot AI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
/* Hide Streamlit toolbar & footer */
[data-testid="stToolbar"]     { display: none !important; }
[data-testid="stDecoration"]  { display: none !important; }
footer                         { display: none !important; }

/* ── Sidebar — wider & dark ── */
section[data-testid="stSidebar"] > div:first-child {
    width: 300px;
    background: #0B1120;
    padding: 1rem 0.85rem;
}
[data-testid="stSidebar"] * { color: #8B9BB4 !important; }
[data-testid="stSidebar"] strong,
[data-testid="stSidebar"] b  { color: #CBD5E1 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #E2E8F0 !important; }

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    background: #161F2E !important;
    border: 1px solid #1E2D45 !important;
    color: #7B8FA6 !important;
    border-radius: 7px !important;
    font-size: 0.78rem !important;
    padding: 0.4rem 0.7rem !important;
    text-align: left !important;
    line-height: 1.35 !important;
    transition: all 0.12s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #1E2D45 !important;
    border-color: #2A4066 !important;
    color: #CBD5E1 !important;
}
[data-testid="stSidebar"] hr { border-color: #1A2640 !important; }
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: #111827 !important;
    border: 1px solid #1E2D45 !important;
    border-radius: 7px !important;
    font-size: 0.75rem !important;
}

/* ── Primary button ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.2px !important;
    height: 2.6rem !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1D4ED8 0%, #1E40AF 100%) !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.35) !important;
}

/* ── Secondary button ── */
.stButton > button[kind="secondary"] {
    border-radius: 8px !important;
    font-size: 0.82rem !important;
    height: 2.1rem !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    border-radius: 12px !important;
    margin-bottom: 0.5rem !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
}

/* ── Chat input ── */
[data-testid="stChatInput"] {
    border-radius: 14px !important;
}
[data-testid="stChatInput"] textarea {
    border-radius: 12px !important;
    border: 1.5px solid #2A3F5F !important;
    font-size: 0.88rem !important;
    background: #0D1B2A !important;
    color: #E2E8F0 !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #3B82F6 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.15) !important;
}

/* ── Selectbox ── */
[data-baseweb="select"] > div {
    border-radius: 9px !important;
    border-color: #2A3F5F !important;
    font-size: 0.88rem !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    border-radius: 10px !important;
    padding: 0.7rem 0.85rem !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] summary {
    font-size: 0.8rem !important;
}

/* ── Info / warning / success boxes ── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    font-size: 0.84rem !important;
}
</style>
""", unsafe_allow_html=True)


# ── Constants & helpers ────────────────────────────────────────────────────────
PLAN_ICON  = {"Enterprise": "⭐", "Growth": "🌱", "Standard": "📦", "internal": "🔑"}
TOOL_META  = {
    "search_documents": ("🔍", "Doc Search"),
    "lookup_data":      ("📊", "Data Lookup"),
    "execute_action":   ("⚡", "Action"),
}

def _get_plan(account_id: str) -> str:
    try:
        c = sqlite3.connect(config.DB_PATH)
        r = c.execute("SELECT plan FROM accounts WHERE account_id=?", (account_id,)).fetchone()
        c.close()
        return r[0] if r else "Standard"
    except Exception:
        return "Standard"

def _plan_tag(plan: str) -> str:
    colors = {
        "Enterprise": ("⭐", "#854D0E", "#FEF9C3"),
        "Growth":     ("🌱", "#166534", "#DCFCE7"),
        "Standard":   ("📦", "#1E40AF", "#DBEAFE"),
        "internal":   ("🔑", "#6B21A8", "#F3E8FF"),
    }
    icon, fg, bg = colors.get(plan, ("📦", "#374151", "#F3F4F6"))
    return (f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:20px;'
            f'font-size:0.7rem;font-weight:600;white-space:nowrap;">{icon} {plan}</span>')


# ── Session state ──────────────────────────────────────────────────────────────
def _init():
    for k, v in dict(
        logged_in=False, account_id=None, company_name=None,
        plan=None, is_internal=False, session_id=None,
        orchestrator=None, messages=[], pending_action=None, tool_log=[],
    ).items():
        st.session_state.setdefault(k, v)
_init()


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN  — compact, single screen, no scroll
# ══════════════════════════════════════════════════════════════════════════════
def show_login():
    # 3-col centering trick
    _, col, _ = st.columns([1, 1.3, 1])
    with col:
        # ── Brand ──
        st.markdown(
            '<div style="text-align:center;padding:2rem 0 1rem;">'
            '<div style="display:inline-block;background:#1E3A5F;width:54px;height:54px;'
            'border-radius:14px;line-height:54px;font-size:1.6rem;margin-bottom:0.6rem;">📦</div>'
            '<h2 style="margin:0;font-size:1.35rem;font-weight:800;letter-spacing:-0.3px;">'
            'ParcelPilot AI</h2>'
            '<p style="margin:3px 0 0;font-size:0.78rem;opacity:0.55;">'
            'Intelligent Logistics Support</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Role ──
        role = st.radio(
            "Sign in as",
            ["👤  Customer", "🔑  Internal Agent"],
            horizontal=True,
            label_visibility="collapsed",
        )
        is_internal = "Internal" in role

        # ── Account picker ──
        if not is_internal:
            customers = {k: v for k, v in config.DEMO_ACCOUNTS.items() if v["role"] == "customer"}
            chosen = st.selectbox(
                "Account",
                list(customers.keys()),
                format_func=lambda k: f"{customers[k]['company']}  ({k})",
                label_visibility="collapsed",
            )
            plan = _get_plan(chosen)
            st.markdown(
                f'<div style="border:1px solid rgba(255,255,255,0.1);border-radius:9px;'
                f'padding:0.55rem 0.8rem;display:flex;justify-content:space-between;'
                f'align-items:center;margin:4px 0 8px;background:rgba(255,255,255,0.03);">'
                f'<div>'
                f'<div style="font-weight:600;font-size:0.85rem;">{customers[chosen]["company"]}</div>'
                f'<div style="font-size:0.68rem;opacity:0.45;font-family:monospace;">{chosen}</div>'
                f'</div>'
                f'{_plan_tag(plan)}'
                f'</div>',
                unsafe_allow_html=True,
            )
            account_id = chosen
        else:
            account_id = "INTERNAL"
            st.markdown(
                '<div style="border:1px solid rgba(139,92,246,0.35);border-radius:9px;'
                'padding:0.55rem 0.85rem;background:rgba(139,92,246,0.07);margin:4px 0 8px;">'
                '<div style="font-weight:600;font-size:0.85rem;color:#A78BFA;">🔑 ParcelPilot Ops</div>'
                '<div style="font-size:0.72rem;opacity:0.5;margin-top:1px;">Full access — all accounts visible</div>'
                '</div>',
                unsafe_allow_html=True,
            )

        # ── CTA ──
        if st.button("Start Session  →", type="primary", use_container_width=True):
            _do_login(account_id)

        st.markdown(
            '<p style="text-align:center;font-size:0.68rem;opacity:0.35;margin-top:0.6rem;">'
            'Dataset snapshot · <code>2026-08-16 11:00 IST</code></p>',
            unsafe_allow_html=True,
        )


def _do_login(account_id: str):
    info = config.DEMO_ACCOUNTS.get(account_id)
    if not info:
        st.error("Unknown account.")
        return
    plan = _get_plan(account_id) if account_id != "INTERNAL" else "internal"
    sid  = str(uuid.uuid4())
    orch = Orchestrator(
        account_id=account_id,
        is_internal=(info["role"] == "internal"),
        session_id=sid,
    )
    st.session_state.update(
        logged_in=True, account_id=account_id,
        company_name=info["company"], plan=plan,
        is_internal=(info["role"] == "internal"),
        session_id=sid, orchestrator=orch,
    )
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
def show_sidebar():
    with st.sidebar:
        # Brand
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;'
            'padding-bottom:0.75rem;border-bottom:1px solid #1A2640;margin-bottom:0.75rem;">'
            '<span style="font-size:1.1rem;">📦</span>'
            '<span style="font-weight:700;font-size:0.95rem;color:#CBD5E1;">ParcelPilot AI</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Account card — compact
        plan  = st.session_state.plan or "Standard"
        icon  = PLAN_ICON.get(plan, "📦")
        snap  = config.get_snapshot_time()
        company = st.session_state.company_name
        acct_id = st.session_state.account_id

        st.markdown(
            f'<div style="background:#111827;border:1px solid #1E2D45;border-radius:9px;'
            f'padding:0.65rem 0.8rem;margin-bottom:0.75rem;">'
            f'<div style="font-weight:700;font-size:0.88rem;color:#E2E8F0;">{company}</div>'
            f'<div style="font-family:monospace;font-size:0.65rem;color:#4B6282;margin-top:1px;">{acct_id}</div>'
            f'<div style="margin-top:6px;font-size:0.7rem;color:#6B8099;">{icon} {plan}</div>'
            f'<div style="margin-top:5px;padding-top:5px;border-top:1px solid #1A2640;'
            f'font-size:0.62rem;color:#4B6282;">⏱ <code style="color:#5A7A9A;">{snap}</code></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Quick prompts
        st.markdown(
            '<div style="font-size:0.62rem;font-weight:600;color:#3D5A7A;'
            'text-transform:uppercase;letter-spacing:0.7px;margin-bottom:5px;">Quick Prompts</div>',
            unsafe_allow_html=True,
        )
        for p in _quick_prompts():
            if st.button(p, use_container_width=True, key=f"qp_{p}"):
                st.session_state._inject = p
                st.rerun()

        st.markdown('<hr style="margin:0.6rem 0;">', unsafe_allow_html=True)

        # Tool activity
        st.markdown(
            '<div style="font-size:0.62rem;font-weight:600;color:#3D5A7A;'
            'text-transform:uppercase;letter-spacing:0.7px;margin-bottom:5px;">Tool Activity</div>',
            unsafe_allow_html=True,
        )
        log = st.session_state.tool_log
        if not log:
            st.markdown('<div style="font-size:0.73rem;color:#3D5A7A;padding:2px 0;">No tools called yet.</div>',
                        unsafe_allow_html=True)
        else:
            for entry in reversed(log[-10:]):
                icon_t, label = TOOL_META.get(entry["name"], ("🔧", entry["name"]))
                with st.expander(f"{icon_t} {label} · {entry['turn']}", expanded=False):
                    st.json({"in": entry["inputs"], "out": entry["output"]}, expanded=False)

        st.markdown('<hr style="margin:0.6rem 0;">', unsafe_allow_html=True)

        # Bottom controls
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑 Clear", use_container_width=True):
                st.session_state.messages = []
                st.session_state.tool_log = []
                st.session_state.pending_action = None
                if st.session_state.orchestrator:
                    st.session_state.orchestrator.reset()
                st.rerun()
        with c2:
            if st.button("← Exit", use_container_width=True):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                _init()
                st.rerun()


def _quick_prompts() -> list[str]:
    acct = st.session_state.account_id
    if st.session_state.is_internal:
        return ["Show proactive issue report", "Which tickets breached SLA?",
                "List all pending cancellations", "List all open tickets"]
    if acct == "ACCT-001":
        return ["Can I cancel ORD-1001 without a fee?", "What are my SLA targets?",
                "Show my open orders", "Status of TKT-501?"]
    if acct == "ACCT-002":
        return ["Is ORD-2002 eligible for a service credit?",
                "Why is bulk CSV upload failing?",
                "Show my open tickets", "What is my cancellation policy?"]
    return ["Show my open orders", "What are my SLA terms?",
            "Check my credit balance", "What is my cancellation policy?"]


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT
# ══════════════════════════════════════════════════════════════════════════════
def show_chat():
    show_sidebar()

    # ── Header ──
    plan    = st.session_state.plan or "Standard"
    icon    = PLAN_ICON.get(plan, "📦")
    snap    = config.get_snapshot_time()
    company = st.session_state.company_name
    acct_id = st.session_state.account_id

    left, right = st.columns([3, 1])
    with left:
        st.markdown(
            f'<div style="padding:0.1rem 0 0.5rem;">'
            f'<span style="font-size:1.15rem;font-weight:700;">'
            f'📦 {company} Support</span>'
            f'<span style="margin-left:10px;font-size:0.72rem;opacity:0.45;'
            f'font-family:monospace;">{acct_id}</span>&nbsp;'
            f'{_plan_tag(plan)}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f'<div style="text-align:right;padding-top:0.15rem;'
            f'font-size:0.68rem;opacity:0.4;">⏱ <code>{snap}</code></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Stats row (internal agents) ──
    if st.session_state.is_internal:
        _show_stats()

    # ── First-load welcome ──
    if not st.session_state.messages:
        body = (
            "Hi! I'm your **internal ops assistant** with full access to all accounts.\n\n"
            "I surface **SLA breaches**, **missed pickups**, **incorrect historical resolutions**, "
            "and pending cancellations. Use quick prompts or ask anything."
            if st.session_state.is_internal else
            f"Hi! Welcome to **ParcelPilot Support** 👋\n\n"
            f"I'm your AI assistant for **{company}** ({plan} plan). I can help with:\n"
            f"- 📦 **Orders** — status, cancellations, pickup issues\n"
            f"- 💳 **Credits** — service credit eligibility & application\n"
            f"- 🎫 **Tickets** — open issues and escalations\n"
            f"- 📄 **Policies** — SLA terms, cancellation rules, refund windows\n\n"
            f"What can I help you with today?"
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": body, "tool_calls": [], "conflicts": []}
        )

    # ── Inject quick prompt ──
    injected = getattr(st.session_state, "_inject", None)
    if injected:
        del st.session_state._inject
        _submit(injected)
        return

    # ── Message history ──
    for msg in st.session_state.messages:
        _render_msg(msg)

    # ── Pending confirmation ──
    _show_confirmation()

    # ── Input ──
    if not st.session_state.pending_action:
        user_input = st.chat_input("Ask about orders, policies, credits, SLA…")
        if user_input:
            _submit(user_input)


def _show_stats():
    try:
        c = sqlite3.connect(config.DB_PATH)
        open_t   = c.execute("SELECT COUNT(*) FROM tickets WHERE LOWER(status) NOT IN ('closed','resolved')").fetchone()[0]
        cancels  = c.execute("SELECT COUNT(*) FROM orders WHERE cancellation_requested_at IS NOT NULL AND UPPER(status) IN ('BOOKED','PICKED_UP')").fetchone()[0]
        missed   = c.execute("SELECT COUNT(*) FROM orders WHERE UPPER(status)='BOOKED' AND pickup_window_end < '2026-08-16 11:00' AND pickup_actual_at IS NULL").fetchone()[0]
        accounts = c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        c.close()
    except Exception:
        open_t = cancels = missed = accounts = 0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎫 Open Tickets",    open_t,  delta="needs attention" if open_t > 3 else None, delta_color="inverse")
    m2.metric("🚫 Pending Cancels", cancels)
    m3.metric("📭 Missed Pickups",  missed,  delta="carrier fault" if missed else None, delta_color="inverse")
    m4.metric("🏢 Accounts",        accounts)
    st.markdown("")


def _render_msg(msg: dict):
    role = msg["role"]
    with st.chat_message(role, avatar="🧑" if role == "user" else "🤖"):
        st.markdown(msg["content"])

        tcs = msg.get("tool_calls", [])
        if tcs:
            # Compact "used" line
            used = "  ·  ".join(
                f"{TOOL_META.get(t.name, ('🔧',''))[0]} "
                f"**{TOOL_META.get(t.name, ('','?'))[1]}**"
                for t in tcs
            )
            st.caption(f"Tools used: {used}")
            with st.expander("📎 Sources & details", expanded=False):
                for tc in tcs:
                    icon_t, label = TOOL_META.get(tc.name, ("🔧", tc.name))
                    st.markdown(f"**{icon_t} {label}**")
                    if tc.name == "search_documents" and "results" in tc.output:
                        for r in tc.output["results"][:3]:
                            dep = " ⚠️ DEPRECATED" if r.get("is_deprecated") else ""
                            st.markdown(
                                f"- **{r['source']}{dep}** "
                                f"— authority `{r['authority_level']}` "
                                f"· relevance `{r['relevance_score']:.2f}`"
                            )
                            st.caption(r["content"][:280] + "…")
                    else:
                        st.json(tc.output, expanded=False)

        for conflict in msg.get("conflicts", []):
            if conflict["type"] == "agreement_override":
                st.success(f"✅ **Agreement override:** {conflict['message']}")
            elif conflict["type"] == "version_conflict":
                st.warning(f"⚠️ **Version conflict:** {conflict['message']}")


def _show_confirmation():
    pa = st.session_state.pending_action
    if not pa:
        return
    st.warning(
        f"**⚡ Confirm Action**\n\n{pa['summary']}\n\n"
        "_This action has NOT been executed yet. Confirm to proceed._",
    )
    c1, c2, _, _ = st.columns([1, 1, 1, 3])
    with c1:
        if st.button("✅ Confirm", type="primary", use_container_width=True, key="confirm_btn"):
            _handle_confirm(pa["action_id"], True)
    with c2:
        if st.button("❌ Cancel", use_container_width=True, key="cancel_btn"):
            _handle_confirm(pa["action_id"], False)


def _handle_confirm(action_id: str, confirmed: bool):
    orch: Orchestrator = st.session_state.orchestrator
    response = orch.notify_confirmation(action_id, confirmed)
    turn = f"Turn {len(st.session_state.messages) + 1}"
    for tc in response.tool_calls:
        st.session_state.tool_log.append(
            {"name": tc.name, "inputs": tc.inputs, "output": tc.output, "turn": turn}
        )
    conflicts = [c for tc in response.tool_calls if tc.name == "search_documents"
                 for c in tc.output.get("conflicts", [])]
    st.session_state.messages.append({
        "role": "assistant", "content": response.text,
        "tool_calls": response.tool_calls, "conflicts": conflicts,
    })
    st.session_state.pending_action = None
    st.rerun()


def _submit(text: str):
    st.session_state.messages.append({"role": "user", "content": text})
    with st.spinner("Thinking…"):
        orch: Orchestrator = st.session_state.orchestrator
        response = orch.chat(text)
    turn = f"Turn {len(st.session_state.messages)}"
    for tc in response.tool_calls:
        st.session_state.tool_log.append(
            {"name": tc.name, "inputs": tc.inputs, "output": tc.output, "turn": turn}
        )
    conflicts = [c for tc in response.tool_calls if tc.name == "search_documents"
                 for c in tc.output.get("conflicts", [])]
    st.session_state.messages.append({
        "role": "assistant", "content": response.text,
        "tool_calls": response.tool_calls, "conflicts": conflicts,
    })
    if response.pending_action:
        st.session_state.pending_action = response.pending_action
    st.rerun()


# ── Entry ──────────────────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    show_login()
else:
    show_chat()
