import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { ApiError, apiRequest } from './api';
import { randomId, sha256Hex } from './browserCrypto';
export type Row = Record<string, unknown>;
export const obj = (v: unknown): Row =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Row) : {};
export const rows = (v: unknown): Row[] => (Array.isArray(v) ? v.map(obj) : []);
export const str = (v: unknown, fallback = '') => (typeof v === 'string' ? v : fallback);
export const num = (v: unknown, fallback = 0) => (typeof v === 'number' ? v : fallback);
export const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((s): s is string => typeof s === 'string') : [];
export function queryPath(path: string, values: Row) {
  const q = new URLSearchParams();
  Object.entries(values).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '')
      q.set(k, typeof v === 'object' ? JSON.stringify(v) : String(v));
  });
  return `${path}?${q}`;
}
function pollDelay(error: unknown, failures: number): number | false {
  if (
    error instanceof ApiError &&
    error.status >= 400 &&
    error.status < 500 &&
    error.status !== 429
  )
    return false;
  if (error instanceof ApiError && error.retryAfter) {
    const seconds = Number(error.retryAfter);
    const delay = Number.isFinite(seconds)
      ? seconds * 1000
      : Date.parse(error.retryAfter) - Date.now();
    if (Number.isFinite(delay)) return Math.max(1000, delay);
  }
  return error ? Math.min(60000, 5000 * 2 ** Math.min(failures, 4)) : 5000;
}
export function useResource(path: string | null, body?: unknown, poll = false) {
  return useQuery({
    queryKey: ['api', path, body],
    queryFn: ({ signal }) =>
      apiRequest<Row>(path!, { signal, ...(body === undefined ? {} : { method: 'POST', body }) }),
    enabled: path !== null,
    retry: false,
    refetchInterval: (query) => {
      if (!poll) return false;
      if (
        path &&
        /^\/(jobs|reports|analyses)\/[^/]+$/.test(path) &&
        ['succeeded', 'failed', 'cancelled', 'expired'].includes(str(query.state.data?.status))
      )
        return false;
      return pollDelay(query.state.error, query.state.fetchFailureCount);
    },
  });
}
export function useList(path: string | null, poll = false) {
  const q = useInfiniteQuery({
    queryKey: ['api', path, 'list'],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      apiRequest<{ items: Row[]; next_cursor: string | null }>(
        `${path}${pageParam ? `${path!.includes('?') ? '&' : '?'}cursor=${encodeURIComponent(pageParam)}` : ''}`,
        { signal },
      ),
    getNextPageParam: (p) => p.next_cursor || undefined,
    enabled: path !== null,
    retry: false,
    refetchInterval: (query) =>
      poll ? pollDelay(query.state.error, query.state.fetchFailureCount) : false,
  });
  return { ...q, items: q.data?.pages.flatMap((p) => p.items || []) || [] };
}
export function errorText(e: unknown) {
  return e instanceof ApiError
    ? `${e.status === 503 ? '소유 모듈에 연결할 수 없습니다. ' : ''}${e.message}${e.requestId ? ` · 요청 ${e.requestId}` : ''}`
    : e instanceof Error
      ? e.message
      : '서버 연결을 확인해 주세요.';
}
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  if (v && typeof v === 'object')
    return `{${Object.entries(v)
      .filter(([, x]) => x !== undefined)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, x]) => `${JSON.stringify(k)}:${canonical(x)}`)
      .join(',')}}`;
  return JSON.stringify(v) ?? 'null';
}
export function useCommand() {
  const client = useQueryClient(),
    lock = useRef(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function run<T = Row>(
    path: string,
    body: unknown,
    options: { method?: string; version?: number; idempotent?: boolean } = {},
  ): Promise<T | undefined> {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    let storage = '';
    try {
      let receipt: { key: string; version?: number } | undefined;
      if (options.idempotent !== false) {
        storage = `dsx-pending-${sha256Hex(canonical(['1.3', options.method || 'POST', path, body]))}`;
        receipt = JSON.parse(sessionStorage.getItem(storage) || 'null') || {
          key: randomId(),
          version: options.version,
        };
        sessionStorage.setItem(storage, JSON.stringify(receipt));
      }
      const result = await apiRequest<T>(path, {
        method: options.method || 'POST',
        body,
        version: receipt ? receipt.version : options.version,
        idempotencyKey: receipt?.key,
      });
      if (storage) sessionStorage.removeItem(storage);
      await client.invalidateQueries({ queryKey: ['api'] });
      return result;
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 429) {
        if (storage) sessionStorage.removeItem(storage);
      }
      if (e instanceof ApiError && e.status === 412)
        await client.invalidateQueries({ queryKey: ['api'] });
      setError(errorText(e));
      return undefined;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { run, busy, error, setError };
}
export const localInput = (date: Date) =>
  new Date(date.getTime() + 9 * 3600000).toISOString().slice(0, 16);
export const currentRange = (hours = 1) => ({
  start: new Date(Date.now() - hours * 3600000).toISOString(),
  end: new Date().toISOString(),
});
export const purposes = [
  '알려진 오류 조사',
  'GPU → Pod 관계',
  'Pod → GPU 관계',
  '작업 영향 확인',
  '미등록 증상 조사',
  '재발 위치 분석',
  '공통 영향 범위',
  '조치 검토 대상',
  '조치 후 관측',
];
export const topics = [
  '장비·Node 변화',
  '할당 명세·시간',
  '저활동 검토',
  '다중 GPU 편차',
  '반복 사건',
  '사건 당시 작업',
  '배치 대기·용량',
  'Namespace·프로젝트 배분',
  'GPU 에너지',
  '조치 전후 비교',
  '관측 품질',
];
export const purposeId = (i: number) => `R${String(i + 1).padStart(2, '0')}`;
export const topicId = (i: number) => `O${String(i + 1).padStart(2, '0')}`;
