import ReactMarkdown from 'react-markdown';
import type { Message, ToolCall } from '../types';
import { TOOL_META } from '../types';

interface Props { message: Message }

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  const time   = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

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
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
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
                  title={JSON.stringify(tc.inputs, null, 2)}
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
