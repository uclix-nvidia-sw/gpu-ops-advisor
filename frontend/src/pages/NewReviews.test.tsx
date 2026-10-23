import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { NewReviews } from './NewReviews';
import type { Row } from '../lib/live';

const data = vi.hoisted(() => ({
  paths: [] as string[],
  kind: 'action',
  records: [] as Row[],
}));
vi.mock('../lib/store', () => ({
  useApp: () => ({
    mode: 'control',
    canOperate: true,
    scope: { clusters: [{ cluster_id: 'global-cluster', namespaces: null }] },
  }),
}));
vi.mock('../lib/newDraft', () => ({
  useNewDraft: (key: string, initial: unknown) => [
    key.endsWith('/kind') ? data.kind : key.endsWith('/occurred') ? '2026-10-22T10:00' : initial,
    vi.fn(),
  ],
  clearNewDraft: vi.fn(),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useList: (path: string | null) => {
    if (path) data.paths.push(path);
    return {
      items: path?.startsWith('/reviews') ? data.records : [],
      isPending: false,
      isError: false,
    };
  },
  useCommand: () => ({ run: vi.fn(), error: '', busy: false }),
}));
beforeEach(() => {
  data.paths = [];
  data.kind = 'action';
  data.records = [];
});

it('queries action targets only in the stored incident scope at the performed time', () => {
  const scope = { clusters: [{ cluster_id: 'stored-cluster', namespaces: ['training'] }] };
  const html = renderToStaticMarkup(
    <NewReviews id="i1" subject="incident" scope={scope} reviewStatus="unreviewed" />,
  );
  const path = data.paths.find((p) => p.startsWith('/assets'))!;
  const params = new URLSearchParams(path.split('?')[1]);
  expect(JSON.parse(params.get('scope')!)).toEqual(scope);
  expect(params.get('at')).toBe('2026-10-22T01:00:00.000Z');
  expect(path).not.toContain('global-cluster');
  expect(html).toContain('사건 검토 상태: 미검토');
  expect(html).toContain('저장해도 검토 완료나 사건 종결로 바뀌지 않습니다');
});

it('does not substitute global scope when the saved scope is unavailable', () => {
  const html = renderToStaticMarkup(<NewReviews id="i1" subject="incident" />);
  expect(data.paths.some((p) => p.startsWith('/assets'))).toBe(false);
  expect(html).toContain('저장된 범위를 확인할 수 없어 조치 기록을 저장할 수 없습니다');
  expect(html).not.toContain('global-cluster');
});

it('retains old analysis comments as read-only records without loading action targets', () => {
  data.records = [
    {
      id: 'review-1',
      kind: 'comment',
      author: '운영자',
      created_at: '2026-10-22T01:00:00Z',
      body: { text: '기존 분석의 검토 내용' },
    },
  ];
  const html = renderToStaticMarkup(
    <NewReviews
      id="analysis-1"
      subject="job"
      readOnly
      scope={{ clusters: [{ cluster_id: 'saved' }] }}
    />,
  );
  expect(html).toContain('기존 분석의 검토 내용');
  expect(html).toContain('사건 기록과 합치지 않고 원래 대상을 유지합니다');
  expect(html).not.toContain('<form');
  expect(html).not.toContain('정정 기록 작성');
  expect(data.paths.some((p) => p.startsWith('/assets'))).toBe(false);
});
