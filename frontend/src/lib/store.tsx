import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { apiRequest } from './api';
import { currentRange } from './live';
import type { Scope, TimeRange } from './types';
type AppState = {
  mode: 'classic' | 'operations' | 'developer';
  setMode: (mode: 'classic' | 'operations' | 'developer') => void;
  scope: Scope;
  registeredScope: Scope;
  setScope: (s: Scope) => void;
  period: string;
  setPeriod: (s: string) => void;
  timeRange: TimeRange;
  refresh: () => void;
  notify: (s: string) => void;
  toast: string;
  ready: boolean;
  connection: { isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  canOperate: boolean;
  canManage: boolean;
  canKnowledge: boolean;
};
const AppContext = createContext<AppState>(null!);
export function AppProvider({ children }: { children: ReactNode }) {
  const [mode, updateMode] = useState<AppState['mode']>(() => {
    try {
      const saved = localStorage.getItem('gpu-advisor-view');
      return saved === 'operations' || saved === 'developer' ? saved : 'classic';
    } catch {
      return 'classic';
    }
  });
  const client = useQueryClient();
  const connection = useQuery({
    queryKey: ['api', 'clusters'],
    queryFn: () => apiRequest<{ items: Scope['clusters'] }>('/clusters'),
    retry: false,
    refetchInterval: 30000,
  });
  const [selected, setScope] = useState<Scope | null>(null),
    [period, setPeriod] = useState('1h'),
    [tick, setTick] = useState(0),
    [toast, setToast] = useState('');
  const registeredScope: Scope = {
    clusters:
      connection.data?.items.map((c) => ({ cluster_id: c.cluster_id, namespaces: c.namespaces })) ||
      [],
  };
  const scope = selected || registeredScope;
  const timeRange = useMemo(() => currentRange(parseInt(period)), [period, tick]);
  const ready = connection.isSuccess;
  return (
    <AppContext.Provider
      value={{
        mode,
        setMode: (next) => {
          updateMode(next);
          try {
            localStorage.setItem('gpu-advisor-view', next);
          } catch {
            /* View selection still works without browser storage. */
          }
        },
        scope,
        registeredScope,
        setScope,
        period,
        setPeriod,
        timeRange,
        refresh: () => {
          setTick((t) => t + 1);
          void client.invalidateQueries({ queryKey: ['api'] });
        },
        notify: (s) => {
          setToast(s);
          window.setTimeout(() => setToast(''), 5000);
        },
        toast,
        ready,
        connection,
        canOperate: ready && scope.clusters.length > 0,
        canManage: ready,
        canKnowledge: ready,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
export const useApp = () => useContext(AppContext);
