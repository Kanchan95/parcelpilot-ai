import { useState } from 'react';
import { Zap, Bot, BarChart3, CreditCard, Shield, CheckCircle2 } from 'lucide-react';
import { api } from '../api';
import { ACCOUNTS } from '../types';
import type { Session } from '../types';

const BADGE: Record<string, { bg: string; text: string }> = {
  'badge-ent': { bg: '#FEF9C3', text: '#854D0E' },
  'badge-gro': { bg: '#DCFCE7', text: '#166534' },
  'badge-std': { bg: '#DBEAFE', text: '#1E40AF' },
  'badge-int': { bg: '#F3E8FF', text: '#6B21A8' },
};

const FEATURES = [
  { Icon: Zap,        text: 'Real-time order tracking & status updates' },
  { Icon: Bot,        text: 'AI-powered issue resolution with policy lookups' },
  { Icon: BarChart3,  text: 'SLA monitoring with automatic breach alerts' },
  { Icon: CreditCard, text: 'Automated credit management & applications' },
];

const CUSTOMERS = ['ACCT-001', 'ACCT-002', 'ACCT-003', 'ACCT-004'];

interface Props { onLogin: (session: Session) => void }

export default function LoginPage({ onLogin }: Props) {
  const [role, setRole]       = useState<'customer' | 'internal'>('customer');
  const [accountId, setAccId] = useState('ACCT-001');
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  const selected = ACCOUNTS[accountId];
  const badgeStyle = selected ? BADGE[selected.badgeCls] : null;

  async function handleLogin() {
    setLoading(true);
    setError('');
    try {
      const id = role === 'internal' ? 'INTERNAL' : accountId;
      const session = await api.login(id);
      onLogin(session);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden">

      {/* ── Left brand panel (dark) ── */}
      <div
        className="hidden md:flex w-[44%] flex-shrink-0 flex-col justify-center px-12 py-16 relative overflow-hidden border-r border-slate-800"
        style={{ background: 'linear-gradient(145deg,#050B18 0%,#091628 55%,#0C1F40 100%)' }}
      >
        {/* Glow blobs */}
        <div className="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full pointer-events-none"
             style={{ background: 'radial-gradient(circle,rgba(37,99,235,.12) 0%,transparent 65%)' }} />
        <div className="absolute -bottom-20 -left-20 w-[350px] h-[350px] rounded-full pointer-events-none"
             style={{ background: 'radial-gradient(circle,rgba(37,99,235,.07) 0%,transparent 65%)' }} />

        {/* Brand */}
        <div className="flex items-center justify-center w-14 h-14 rounded-2xl text-2xl mb-5"
             style={{ background: 'linear-gradient(135deg,#1A3A60,#2563EB)', boxShadow: '0 8px 20px rgba(37,99,235,.4)' }}>
          📦
        </div>
        <h1 className="text-[2rem] font-extrabold tracking-tight mb-1 text-white" style={{ letterSpacing: '-0.4px' }}>
          ParcelPilot AI
        </h1>
        <p className="text-sm mb-10 text-slate-500">Intelligent logistics support, powered by AI</p>

        {/* Features */}
        <div className="flex flex-col gap-3">
          {FEATURES.map(({ Icon, text }) => (
            <div key={text}
                 className="flex items-center gap-3 px-4 py-3 rounded-xl"
                 style={{ background: 'rgba(255,255,255,.035)', border: '1px solid rgba(255,255,255,.055)' }}>
              <div className="flex items-center justify-center w-9 h-9 rounded-[9px] flex-shrink-0"
                   style={{ background: 'rgba(37,99,235,.14)' }}>
                <Icon size={16} className="text-blue-400" />
              </div>
              <span className="text-[0.82rem] font-medium text-slate-400">{text}</span>
            </div>
          ))}
        </div>

        {/* Trust footer */}
        <div className="mt-10 pt-6 border-t border-slate-800 flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-slate-600 text-[0.72rem]">
            <Shield size={12} /> Role-based access control
          </div>
          <div className="flex items-center gap-1.5 text-slate-600 text-[0.72rem]">
            <CheckCircle2 size={12} /> Policy-grounded answers
          </div>
        </div>
      </div>

      {/* ── Right form panel (light) ── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-[390px]">

          {/* Mobile logo */}
          <div className="md:hidden flex items-center gap-2.5 mb-7">
            <div className="w-9 h-9 rounded-xl text-lg flex items-center justify-center"
                 style={{ background: 'linear-gradient(135deg,#1A3A60,#2563EB)' }}>📦</div>
            <span className="font-bold text-slate-900">ParcelPilot AI</span>
          </div>

          <h2 className="text-[1.6rem] font-bold tracking-tight text-slate-900 mb-1">Welcome back</h2>
          <p className="text-[0.85rem] text-slate-500 mb-7">Sign in to access your support dashboard</p>

          {/* Role toggle */}
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.5px] text-slate-400 mb-1.5">Sign in as</p>
          <div className="flex p-1 rounded-xl mb-5 bg-slate-100 border border-slate-200">
            {(['customer', 'internal'] as const).map(r => (
              <button
                key={r}
                onClick={() => setRole(r)}
                className={`flex-1 py-2 px-3 rounded-[9px] text-[0.8rem] font-medium transition-all ${
                  role === r
                    ? 'bg-white text-slate-900 shadow-sm border border-slate-200'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {r === 'customer' ? '👤 Customer' : '🔑 Internal Agent'}
              </button>
            ))}
          </div>

          {/* Customer section */}
          {role === 'customer' ? (
            <>
              <p className="text-[0.72rem] font-semibold uppercase tracking-[0.5px] text-slate-400 mb-1.5">Account</p>
              <select
                value={accountId}
                onChange={e => setAccId(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-[10px] text-[0.86rem] mb-3 border border-slate-200 bg-white text-slate-900 appearance-none cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                style={{
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='11' height='7' viewBox='0 0 11 7'%3E%3Cpath d='M1 1l4.5 4.5L10 1' stroke='%2394A3B8' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
                  backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center',
                }}
              >
                {CUSTOMERS.map(id => (
                  <option key={id} value={id}>{ACCOUNTS[id].name}</option>
                ))}
              </select>

              {selected && badgeStyle && (
                <div className="flex items-center justify-between px-3.5 py-3 rounded-[10px] mb-4 border border-slate-200 bg-slate-50">
                  <div>
                    <p className="font-semibold text-[0.86rem] text-slate-900">{selected.name}</p>
                    <p className="text-[0.67rem] font-mono mt-0.5 text-slate-400">{accountId}</p>
                  </div>
                  <span className="text-[0.67rem] font-semibold px-2.5 py-1 rounded-full"
                        style={{ background: badgeStyle.bg, color: badgeStyle.text }}>
                    {selected.badgeText}
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="px-3.5 py-3 rounded-[10px] mb-4 border bg-purple-50 border-purple-200">
              <p className="font-semibold text-[0.86rem] text-purple-700">🔑 ParcelPilot Ops</p>
              <p className="text-[0.7rem] mt-0.5 text-purple-500">Full access · All accounts visible</p>
            </div>
          )}

          {error && (
            <p className="text-[0.8rem] mb-3 px-3 py-2 rounded-lg border text-red-700 bg-red-50 border-red-200">{error}</p>
          )}

          <button
            onClick={handleLogin}
            disabled={loading}
            className="w-full py-3 rounded-[10px] text-white font-semibold text-[0.9rem] transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-lg"
            style={{ background: 'linear-gradient(135deg,#2563EB,#1D4ED8)', boxShadow: '0 4px 14px rgba(37,99,235,.25)' }}
          >
            {loading ? 'Connecting…' : 'Start Session →'}
          </button>

          <div className="flex items-center justify-center gap-1.5 mt-5">
            <Shield size={11} className="text-slate-300" />
            <p className="text-[0.68rem] text-slate-400">Secure · Role-based · Policy-grounded</p>
          </div>
        </div>
      </div>
    </div>
  );
}
