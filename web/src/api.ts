import type { Session, ChatResponse } from './types';

const BASE = '';  // Vite proxies /api → localhost:8080

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r.json();
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export const api = {
  login: (account_id: string): Promise<Session> =>
    post('/api/login', { account_id }),

  chat: (session_id: string, message: string): Promise<ChatResponse> =>
    post('/api/chat', { session_id, message }),

  confirm: (session_id: string, action_id: string, confirmed: boolean): Promise<ChatResponse> =>
    post('/api/confirm', { session_id, action_id, confirmed }),

  stats: (session_id: string): Promise<Record<string, number>> =>
    get(`/api/stats?session_id=${session_id}`),

  logout: (session_id: string): Promise<void> =>
    post('/api/logout', { session_id }),
};
