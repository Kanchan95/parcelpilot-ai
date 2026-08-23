import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message, ToolCall, DocSearchOutput, DocSearchResult, DocSearchConflict } from '../types';
import { TOOL_META, SOURCE_TYPE_LABELS } from '../types';

interface Props { message: Message }

// ── Sources panel ─────────────────────────────────────────────────────────────

function sourceIcon(r: DocSearchResult): string {
  if (r.is_deprecated) return '⚠️';
  if (r.source_type === 'customer_agreement') return '📋';
  return '📄';
}

function SourcesPanel({ output }: { output: DocSearchOutput }) {
  const [open, setOpen] = useState(false);
  const { results, conflicts } = output;
  if (!results || results.length === 0) return null;

  const hasConflicts = conflicts && conflicts.length > 0;

  return (
    <div className="mt-1 rounded-xl border overflow-hidden"
         style={{ borderColor: '#E2E8F0', background: '#F8FAFC', fontSize: '0.75rem' }}>
      {/* Toggle header */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left transition-colors"
        style={{ color: '#475569', background: open ? '#F1F5F9' : 'transparent' }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = '#F1F5F9'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = open ? '#F1F5F9' : 'transparent'; }}
      >
        <span className="font-medium flex items-center gap-1.5">
          📚 Sources ({results.length})
          {hasConflicts && (
            <span className="text-[0.65rem] px-1.5 py-0.5 rounded-full font-semibold"
                  style={{ background: '#FEF3C7', color: '#92400E' }}>
              ⚠️ conflict
            </span>
          )}
        </span>
        <span style={{ color: '#94A3B8' }}>{open ? '▲' : '▼'}</span>
      </button>

      {/* Expanded body */}
      {open && (
        <div className="px-3 pb-3 pt-1 flex flex-col gap-2">
          {/* Conflict notices */}
          {hasConflicts && conflicts.map((c: DocSearchConflict, i: number) => (
            <div key={i} className="rounded-lg px-3 py-2 text-[0.72rem] leading-relaxed"
                 style={{ background: '#FFFBEB', border: '1px solid #FDE68A', color: '#92400E' }}>
              {c.type === 'agreement_override'
                ? '📋 Customer agreement takes precedence: '
                : '🔄 Version conflict: '}
              {c.message}
            </div>
          ))}

          {/* Document list */}
          {results.map((r: DocSearchResult, i: number) => (
            <div key={i} className="rounded-lg px-3 py-2"
                 style={{
                   background: r.is_deprecated ? '#FFF7ED' : '#FFFFFF',
                   border: `1px solid ${r.is_deprecated ? '#FED7AA' : '#E2E8F0'}`,
                 }}>
              <div className="flex items-start justify-between gap-2">
                <span className="font-semibold leading-snug" style={{ color: r.is_deprecated ? '#9A3412' : '#1E293B' }}>
                  {sourceIcon(r)} {r.source}
                </span>
                <span className="flex-shrink-0 text-[0.62rem] px-1.5 py-0.5 rounded-full font-mono"
                      style={{ background: '#EFF6FF', color: '#1D4ED8' }}>
                  A{r.authority_level}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[0.65rem]" style={{ color: '#64748B' }}>
                  {SOURCE_TYPE_LABELS[r.source_type] ?? r.source_type}
                </span>
                {r.is_deprecated && (
                  <span className="text-[0.62rem] font-semibold" style={{ color: '#EA580C' }}>
                    DEPRECATED
                  </span>
                )}
                <span className="text-[0.62rem]" style={{ color: '#94A3B8' }}>
                  relevance {(r.relevance_score * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  const time   = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  // Extract document search output from tool calls (if any)
  const docSearchTc = !isUser && message.toolCalls
    ? message.toolCalls.find((tc: ToolCall) => tc.name === 'search_documents')
    : undefined;
  const docSearchOutput = docSearchTc
    ? (docSearchTc.output as unknown as DocSearchOutput)
    : null;

  return (
    <div className={`flex gap-2.5 max-w-[82%] ${isUser ? 'self-end flex-row-reverse' : 'self-start'}`}>
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center text-[0.78rem] flex-shrink-0 mt-0.5"
        style={isUser
          ? { background: '#2563EB' }
          : { background: '#F1F5F9', border: '1px solid #E2E8F0' }}
      >
        {isUser ? '🧑' : '🤖'}
      </div>

      {/* Content */}
      <div className="flex flex-col gap-1">
        <div
          className={`px-4 py-3 rounded-2xl text-[0.86rem] leading-relaxed ${
            isUser ? 'rounded-br-sm' : 'rounded-bl-sm'
          }`}
          style={isUser
            ? { background: '#2563EB', color: '#fff' }
            : { background: '#FFFFFF', border: '1px solid #E2E8F0', color: '#1E293B', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
        >
          {isUser ? (
            <p style={{ margin: 0 }}>{message.content}</p>
          ) : (
            <div className="prose">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          )}

          {/* Sources panel — inline inside the bubble for assistant messages */}
          {!isUser && docSearchOutput && (
            <SourcesPanel output={docSearchOutput} />
          )}
        </div>

        {/* Tool chips */}
        {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-0.5 pl-1">
            {message.toolCalls.map((tc: ToolCall, i) => {
              const meta = TOOL_META[tc.name] ?? { icon: '🔧', label: tc.name };
              return (
                <span
                  key={i}
                  className="text-[0.63rem] px-2 py-0.5 rounded-full border bg-slate-50 text-slate-500 border-slate-200"
                >
                  {meta.icon} {meta.label}
                </span>
              );
            })}
          </div>
        )}

        <span className={`text-[0.6rem] text-slate-400 px-1 ${isUser ? 'text-right' : ''}`}>{time}</span>
      </div>
    </div>
  );
}
