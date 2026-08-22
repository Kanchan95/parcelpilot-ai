import { useState } from 'react';
import type { Session } from './types';
import LoginPage from './components/LoginPage';
import ChatApp from './components/ChatApp';
import './index.css';

export default function App() {
  const [session, setSession] = useState<Session | null>(null);

  if (!session) {
    return <LoginPage onLogin={setSession} />;
  }

  return <ChatApp session={session} onLogout={() => setSession(null)} />;
}
