import type { Session, ChatResponse } from './types';

const BASE = '';  // Vite proxies /api → localhost:8080

async function _extractError(r: Response): Promise<string> {
  try {
    const data = await r.json();
    // Prefer our structured error format, then FastAPI's detail field
    if (typeof data.message === 'string') return data.message;
    if (typeof data.detail === 'string') return data.detail;
    // FastAPI validation errors return detail as an array
    if (Array.isArray(data.detail)) return 'Invalid request. Please try again.';
  } catch {
    // Response body was not JSON — fall through to generic message
  }
  return `Request failed (HTTP ${r.status}). Please try again.`;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await _extractError(r));
  }
  return r.json();
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) {
    throw new Error(await _extractError(r));
  }
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
