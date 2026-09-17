import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useState, type ReactNode } from 'react';
import { allScope, initialDatabase } from '../data/fixtures';
import type { Database, Scope } from './types';
const key = 'dsx-frontend-demo-v1';
function read(): Database {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return JSON.parse(raw);
  } catch {
    /* invalid demo snapshot falls back to fixtures */
  }
  return structuredClone(initialDatabase);
}
export const demoRepository = {
  async reset() {
    localStorage.removeItem(key);
    return structuredClone(initialDatabase);
  },
  async get() {
    return read();
  },
  async change(update: (db: Database) => void) {
    const db = read();
    update(db);
    localStorage.setItem(key, JSON.stringify(db));
    return db;
  },
};
export function useDatabase() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['demo-database'],
    queryFn: demoRepository.get,
    staleTime: 0,
  });
  const mutate = async (update: (db: Database) => void) => {
    const next = await demoRepository.change(update);
    client.setQueryData(['demo-database'], next);
  };
  const reset = async () => {
    client.setQueryData(['demo-database'], await demoRepository.reset());
  };
  return { db: query.data, mutate, reset, isLoading: query.isLoading, error: query.error };
}
type AppState = {
  scope: Scope;
  setScope: (scope: Scope) => void;
  period: string;
  setPeriod: (v: string) => void;
  assistant: boolean;
  setAssistant: (v: boolean) => void;
  assistantContext: string;
  ask: (context: string) => void;
  notify: (text: string) => void;
  toast: string;
  role: string;
  setRole: (s: string) => void;
};
const AppContext = createContext<AppState>(null!);
export function AppProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<Scope>(() => {
    try {
      return JSON.parse(sessionStorage.getItem('dsx-scope') || 'null') || allScope;
    } catch {
      return allScope;
    }
  });
  const [period, setPeriod] = useState('1h');
  const [assistant, setAssistant] = useState(false);
  const [assistantContext, setContext] = useState('일반 질문 · 운영 데이터 참조 없음');
  const [toast, setToast] = useState('');
  const [role, changeRole] = useState(() => {
    const saved = sessionStorage.getItem('dsx-demo-role');
    return saved && ['operator', 'viewer', 'knowledge', 'admin'].includes(saved)
      ? saved
      : 'operator';
  });
  const notify = (s: string) => {
    setToast(s);
    window.setTimeout(() => setToast(''), 4500);
  };
  const setRole = (s: string) => {
    changeRole(s);
    sessionStorage.setItem('dsx-demo-role', s);
    setAssistant(false);
    setContext('일반 질문 · 운영 데이터 참조 없음');
    notify('데모 역할이 변경되었습니다. 실제 권한 검증은 백엔드 연결 후 적용됩니다.');
  };
  return (
    <AppContext.Provider
      value={{
        scope,
        setScope: (s) => {
          setScope(s);
          sessionStorage.setItem('dsx-scope', JSON.stringify(s));
        },
        period,
        setPeriod,
        assistant,
        setAssistant,
        assistantContext,
        ask: (c) => {
          setContext(c);
          setAssistant(true);
        },
        notify,
        toast,
        role,
        setRole,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
export const useApp = () => useContext(AppContext);
