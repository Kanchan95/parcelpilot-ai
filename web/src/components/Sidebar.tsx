import type { Session, ToolLogEntry } from '../types';
import { ACCOUNTS, QUICK_PROMPTS, TOOL_META } from '../types';

const BADGE: Record<string, { bg: string; text: string }> = {
  'badge-ent': { bg: '#FEF9C3', text: '#854D0E' },
  'badge-gro': { bg: '#DCFCE7', text: '#166534' },
  'badge-std': { bg: '#DBEAFE', text: '#1E40AF' },
  'badge-int': { bg: '#F3E8FF', text: '#6B21A8' },
};

interface Props {
  session: Session;
  toolLog: ToolLogEntry[];
  onPrompt: (text: string) => void;
  onClear: () => void;
  onLogout: () => void;
}

export default function Sidebar({ session, toolLog, onPrompt, onClear, onLogout }: Props) {
  const meta   = ACCOUNTS[session.account_id];
  const badge  = meta ? BADGE[meta.badgeCls] : null;
  const prompts = QUICK_PROMPTS[session.account_id] ?? QUICK_PROMPTS['ACCT-001'];

  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-hidden"
      style={{ width: '272px', background: '#1B2A3B', borderRight: '1px solid #2C3E52' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 flex-shrink-0" style={{ height: '54px', borderBottom: '1px solid #2C3E52' }}>
        <div className="flex items-center justify-center w-7 h-7 rounded-lg text-[0.82rem] flex-shrink-0"
             style={{ background: 'linear-gradient(135deg,#1A3A60,#2563EB)' }}>
          📦
        </div>
        <span className="font-bold text-[0.86rem] text-white">ParcelPilot AI</span>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-2.5 py-3">

        <SectionLabel>Account</SectionLabel>
        <div className="rounded-[10px] p-3 mb-1" style={{ background: '#243345', border: '1px solid #2E4259' }}>
          <p className="font-bold text-[0.84rem] text-white">{session.company}</p>
          <p className="font-mono text-[0.63rem] mt-0.5" style={{ color: '#3D5A7A' }}>{session.account_id}</p>
          <div className="flex items-center justify-between mt-2">
            <span className="text-[0.66rem]" style={{ color: '#4B6A8A' }}>{meta?.plan ?? session.plan} Plan</span>
            {badge && (
              <span className="text-[0.66rem] font-semibold px-2 py-0.5 rounded-full"
                    style={{ background: badge.bg, color: badge.text }}>
                {meta?.badgeText}
              </span>
            )}
          </div>
          <div className="mt-2 pt-2" style={{ borderTop: '1px solid #2E4259' }}>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: '#10B981', boxShadow: '0 0 4px #10B981' }} />
              <span className="text-[0.6rem]" style={{ color: '#3D5A7A' }}>Session active</span>
            </div>
            {session.snapshot && (
              <p className="text-[0.6rem] mt-1 leading-tight" style={{ color: '#3D5A7A' }}>
                Reference time: <span className="font-mono" style={{ color: '#4B6A8A' }}>{session.snapshot}</span>
              </p>
            )}
          </div>
        </div>

        <SectionLabel>Quick Prompts</SectionLabel>
        {prompts.map(p => (
          <button
            key={p}
            onClick={() => onPrompt(p)}
            className="w-full text-left px-2.5 py-2 rounded-lg text-[0.74rem] leading-snug mb-0.5 transition-all"
            style={{ background: '#243345', border: '1px solid #2E4259', color: '#8DADC8' }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.background = '#2D4156';
              (e.currentTarget as HTMLElement).style.color = '#CBD5E1';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.background = '#243345';
              (e.currentTarget as HTMLElement).style.color = '#7B9BB8';
            }}
          >
            {p}
          </button>
        ))}

        <SectionLabel>Tool Activity</SectionLabel>
        {toolLog.length === 0 ? (
          <p className="text-[0.71rem] px-1" style={{ color: '#3D5A7A' }}>No tools called yet.</p>
        ) : (
          toolLog.slice(0, 15).map((entry, i) => {
            const m = TOOL_META[entry.name] ?? { icon: '🔧', label: entry.name };
            return (
              <div key={i} className="px-2.5 py-1.5 rounded-lg mb-0.5" style={{ background: '#111827', border: '1px solid #1E2D45' }}>
                <p className="text-[0.71rem] font-semibold" style={{ color: '#7B9BB8' }}>{m.icon} {m.label}</p>
                <p className="text-[0.62rem]" style={{ color: '#3D5A7A' }}>{entry.turn}</p>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div className="flex gap-1.5 p-2.5 flex-shrink-0" style={{ borderTop: '1px solid #2C3E52' }}>
        <SbBtn onClick={onClear} label="🗑 Clear" />
        <SbBtn onClick={onLogout} label="← Exit" danger />
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[0.6rem] font-bold uppercase tracking-[0.8px] px-1 pt-2 pb-1" style={{ color: '#4E6880' }}>
      {children}
    </p>
  );
}

function SbBtn({ onClick, label, danger }: { onClick: () => void; label: string; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className="flex-1 py-1.5 rounded-lg text-[0.73rem] transition-all"
      style={{ background: '#243345', border: '1px solid #2E4259', color: '#6A8DAA' }}
      onMouseEnter={e => {
        if (danger) { e.currentTarget.style.color = '#EF4444'; e.currentTarget.style.borderColor = 'rgba(239,68,68,.35)'; }
        else { e.currentTarget.style.color = '#94A3B8'; }
      }}
      onMouseLeave={e => {
        e.currentTarget.style.color = '#4B6A8A';
        e.currentTarget.style.borderColor = '#1E2D45';
      }}
    >
      {label}
    </button>
  );
}
