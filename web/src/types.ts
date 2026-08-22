export interface Session {
  session_id: string;
  account_id: string;
  company: string;
  plan: string;
  is_internal: boolean;
  snapshot: string;
}

export interface ToolCall {
  name: string;
  inputs: Record<string, unknown>;
  output: Record<string, unknown>;
}

export interface PendingAction {
  action_id: string;
  summary: string;
  status: string;
  [key: string]: unknown;
}

export interface ChatResponse {
  text: string;
  tool_calls: ToolCall[];
  pending_action: PendingAction | null;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
  timestamp: Date;
}

export interface ToolLogEntry {
  name: string;
  inputs: Record<string, unknown>;
  output: Record<string, unknown>;
  turn: string;
}

export type AccountId = 'ACCT-001' | 'ACCT-002' | 'ACCT-003' | 'ACCT-004' | 'INTERNAL';

export interface AccountMeta {
  name: string;
  plan: string;
  badgeCls: string;
  badgeText: string;
}

export const ACCOUNTS: Record<string, AccountMeta> = {
  'ACCT-001': { name: 'Northstar Logistics', plan: 'Enterprise', badgeCls: 'badge-ent', badgeText: '⭐ Enterprise' },
  'ACCT-002': { name: 'LumenWorks',          plan: 'Growth',     badgeCls: 'badge-gro', badgeText: '🌱 Growth' },
  'ACCT-003': { name: 'Beacon Retail',       plan: 'Standard',   badgeCls: 'badge-std', badgeText: '📦 Standard' },
  'ACCT-004': { name: 'Axis Labs',           plan: 'Enterprise', badgeCls: 'badge-ent', badgeText: '⭐ Enterprise' },
  'INTERNAL': { name: 'ParcelPilot Ops',     plan: 'internal',   badgeCls: 'badge-int', badgeText: '🔑 Internal' },
};

export const QUICK_PROMPTS: Record<string, string[]> = {
  'ACCT-001': ['Can I cancel ORD-1001 without a fee?', 'What are my SLA targets?', 'Show my open orders', 'Status of TKT-501?'],
  'ACCT-002': ['Is ORD-2002 eligible for a service credit?', 'Why is bulk CSV upload failing?', 'Show my open tickets', 'What is my cancellation policy?'],
  'ACCT-003': ['Show my open orders', 'What is my cancellation policy?', 'Check my credit balance', 'List my open tickets'],
  'ACCT-004': ['Show my open orders', 'What are my SLA terms?', 'Check my credit balance', 'What is my cancellation policy?'],
  'INTERNAL': ['Show proactive issue report', 'Which tickets breached SLA?', 'List all pending cancellations', 'List all open tickets'],
};

export const TOOL_META: Record<string, { icon: string; label: string }> = {
  search_documents: { icon: '🔍', label: 'Doc Search' },
  lookup_data:      { icon: '📊', label: 'Data Lookup' },
  execute_action:   { icon: '⚡', label: 'Action' },
};
