import { useState, useEffect, useRef, useCallback } from 'react';
import { Send } from 'lucide-react';
import { api } from '../api';
import { ACCOUNTS } from '../types';
import type { Session, Message, PendingAction, ToolLogEntry, ToolCall } from '../types';
import Sidebar from './Sidebar';
import MessageBubble from './MessageBubble';

const BADGE: Record<string, { bg: string; text: string }> = {
  'badge-ent': { bg: '#FEF9C3', text: '#854D0E' },
  'badge-gro': { bg: '#DCFCE7', text: '#166534' },
  'badge-std': { bg: '#DBEAFE', text: '#1E40AF' },
  'badge-int': { bg: '#F3E8FF', text: '#6B21A8' },
};

function mkId() { return Math.random().toString(36).slice(2); }

function welcome(session: Session): string {
  if (session.is_internal) {
    return `Hi! I'm your **internal ops assistant** with full access to all accounts.\n\nI surface **SLA breaches**, **missed pickups**, **stale resolutions**, and pending cancellations. Use the quick prompts or ask anything.`;
  }
  const meta = ACCOUNTS[session.account_id];
  return `Hi! Welcome to **ParcelPilot Support** 👋\n\nI'm your AI assistant for **${session.company}** (${meta?.plan ?? session.plan} plan). I can help with:\n- 📦 **Orders** — status, cancellations, pickup issues\n- 💳 **Credits** — service credit eligibility & application\n- 🎫 **Tickets** — open issues and escalations\n- 📄 **Policies** — SLA terms, cancellation rules, refund windows\n\nWhat can I help you with today?`;
}

interface Props { session: Session; onLogout: () => void }

export default function ChatApp({ session, onLogout }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [toolLog, setToolLog]   = useState<ToolLogEntry[]>([]);
  const [pending, setPending]   = useState<PendingAction | null>(null);
  const [input, setInput]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [stats, setStats]       = useState<Record<string, number>>({});
  const bottomRef               = useRef<HTMLDivElement>(null);
  const taRef                   = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setMessages([{ id: mkId(), role: 'assistant', content: welcome(session), timestamp: new Date() }]);
    if (session.is_internal) {
      api.stats(session.session_id).then(setStats).catch(() => {});
    }
  }, [session]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, pending]);

  const addToolLog = useCallback((toolCalls: ToolCall[], turn: string) => {
    if (!toolCalls.length) return;
    setToolLog(prev => [...toolCalls.map(tc => ({ ...tc, turn })), ...prev].slice(0, 50));
  }, []);

  async function submit(text: string) {
    if (!text.trim() || loading) return;
    setMessages(prev => [...prev, { id: mkId(), role: 'user', content: text, timestamp: new Date() }]);
    setInput('');
    if (taRef.current) taRef.current.style.height = 'auto';
    setLoading(true);
    try {
      const res = await api.chat(session.session_id, text);
      const turn = `Turn ${messages.filter(m => m.role === 'user').length + 1}`;
      addToolLog(res.tool_calls, turn);
      setMessages(prev => [...prev, { id: mkId(), role: 'assistant', content: res.text, toolCalls: res.tool_calls, timestamp: new Date() }]);
      if (res.pending_action) setPending(res.pending_action);
    } catch (e) {
      setMessages(prev => [...prev, { id: mkId(), role: 'assistant', content: `Something went wrong: ${e instanceof Error ? e.message : 'Unknown error'}`, timestamp: new Date() }]);
    } finally {
      setLoading(false);
    }
  }

  async function confirmAction(confirmed: boolean) {
    if (!pending) return;
    const aid = pending.action_id;
    setPending(null);
    setLoading(true);
    try {
      const res = await api.confirm(session.session_id, aid, confirmed);
      addToolLog(res.tool_calls, `Turn ${messages.filter(m => m.role === 'user').length}c`);
      setMessages(prev => [...prev, { id: mkId(), role: 'assistant', content: res.text, toolCalls: res.tool_calls, timestamp: new Date() }]);
      if (res.pending_action) setPending(res.pending_action);
    } catch (e) {
      setMessages(prev => [...prev, { id: mkId(), role: 'assistant', content: `Error: ${e instanceof Error ? e.message : 'Unknown error'}`, timestamp: new Date() }]);
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setMessages([{ id: mkId(), role: 'assistant', content: 'Chat cleared. How can I help you?', timestamp: new Date() }]);
    setToolLog([]); setPending(null);
  }

  async function handleLogout() {
    try { await api.logout(session.session_id); } catch (_) {}
    onLogout();
  }

  const meta  = ACCOUNTS[session.account_id];
  const badge = meta ? BADGE[meta.badgeCls] : null;

  return (
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: '#F0F4F9' }}>
      <Sidebar session={session} toolLog={toolLog} onPrompt={submit} onClear={clearChat} onLogout={handleLogout} />

      {/* Main area */}
      <div className="flex flex-col flex-1 overflow-hidden" style={{ background: '#F0F4F9' }}>

        {/* Header */}
        <header className="flex items-center justify-between px-6 flex-shrink-0 border-b" style={{ height: '54px', background: '#FAFCFF', borderColor: '#DDE3ED' }}>
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-[9px] text-[1rem] bg-blue-50 border border-blue-100">
              💬
            </div>
            <div>
              <p className="font-bold text-[0.92rem] text-slate-900">{session.company} Support</p>
              <p className="text-[0.69rem] text-slate-400 flex items-center gap-1">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" style={{ boxShadow: '0 0 4px #10B981' }} />
                AI Agent · Live
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            {badge && (
              <span className="text-[0.67rem] font-semibold px-2.5 py-0.5 rounded-full"
                    style={{ background: badge.bg, color: badge.text }}>
                {meta?.badgeText}
              </span>
            )}
            <span className="text-[0.72rem] text-slate-400 font-mono">{session.account_id}</span>
          </div>
        </header>

        {/* Stats bar (internal) */}
        {session.is_internal && Object.keys(stats).length > 0 && (
          <div className="flex flex-shrink-0 border-b" style={{ borderColor: '#DDE3ED', background: '#F5F8FC' }}>
            {[
              { icon: '🎫', val: stats.open_tickets,    lbl: 'Open Tickets',     warn: (stats.open_tickets ?? 0) > 3 },
              { icon: '🚫', val: stats.pending_cancels, lbl: 'Pending Cancels',  warn: false },
              { icon: '📭', val: stats.missed_pickups,  lbl: 'Missed Pickups',   warn: (stats.missed_pickups ?? 0) > 0 },
              { icon: '🏢', val: stats.accounts,        lbl: 'Accounts',          warn: false },
            ].map(({ icon, val, lbl, warn }) => (
              <div key={lbl} className="flex-1 flex items-center gap-2.5 px-4 py-2.5 border-r last:border-r-0" style={{ borderColor: '#DDE3ED' }}>
                <span className="text-base">{icon}</span>
                <div>
                  <p className={`text-[1.05rem] font-bold ${warn ? 'text-red-600' : 'text-slate-800'}`}>{val ?? '—'}</p>
                  <p className="text-[0.63rem] text-slate-500">{lbl}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-5" style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', background: '#F0F4F9' }}>
          {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}

          {/* Typing indicator */}
          {loading && (
            <div className="flex gap-2.5 self-start">
              <div className="w-7 h-7 rounded-full flex items-center justify-center text-[0.78rem] bg-slate-100 border border-slate-200">🤖</div>
              <div className="flex items-center gap-1.5 px-4 py-3 rounded-2xl rounded-bl-sm bg-white border border-slate-200 shadow-sm">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-1.5 h-1.5 rounded-full bg-slate-400"
                       style={{ animation: `bounce 1.2s infinite ${i * 0.2}s` }} />
                ))}
              </div>
            </div>
          )}

          {/* Confirmation card */}
          {pending && !loading && (
            <div className="self-start max-w-[88%] rounded-2xl p-4 bg-white border border-amber-300 shadow-sm">
              <p className="font-bold text-[0.86rem] mb-2 text-amber-700">⚡ Confirm Action</p>
              <p className="text-[0.83rem] mb-2 whitespace-pre-wrap leading-relaxed text-slate-700">
                {pending.summary ?? JSON.stringify(pending, null, 2)}
              </p>
              <p className="text-[0.72rem] italic mb-3 text-slate-500">
                This action has NOT been executed. Click Confirm to proceed.
              </p>
              <div className="flex gap-2">
                <button onClick={() => confirmAction(true)}
                  className="px-4 py-1.5 rounded-lg text-white text-[0.8rem] font-semibold bg-green-600 hover:bg-green-700 transition-colors">
                  ✅ Confirm
                </button>
                <button onClick={() => confirmAction(false)}
                  className="px-4 py-1.5 rounded-lg text-[0.8rem] font-semibold border border-slate-200 bg-white text-slate-600 hover:border-red-300 hover:text-red-600 transition-colors">
                  ✗ Cancel
                </button>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="flex-shrink-0 px-6 py-4 border-t" style={{ background: '#FAFCFF', borderColor: '#DDE3ED' }}>
          <div className="flex items-end gap-2 rounded-2xl px-4 py-2 border transition-all focus-within:ring-2 focus-within:ring-blue-100" style={{ background: '#FFFFFF', borderColor: '#DDE3ED' }}>
            <textarea
              ref={taRef}
              rows={1}
              value={input}
              onChange={e => { setInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 130) + 'px'; }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(input); } }}
              placeholder="Ask about orders, policies, credits, SLA…"
              disabled={loading}
              className="flex-1 bg-transparent border-none resize-none text-[0.86rem] leading-relaxed py-0.5 focus:outline-none disabled:opacity-50 text-slate-900 placeholder:text-slate-400"
              style={{ minHeight: '22px', maxHeight: '130px' }}
            />
            <button
              onClick={() => submit(input)}
              disabled={loading || !input.trim()}
              className="flex items-center justify-center w-8 h-8 rounded-[9px] flex-shrink-0 transition-all bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send size={14} color="white" />
            </button>
          </div>
          <p className="text-center text-[0.65rem] mt-1.5 text-slate-400">
            Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
          30% { transform: translateY(-5px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
