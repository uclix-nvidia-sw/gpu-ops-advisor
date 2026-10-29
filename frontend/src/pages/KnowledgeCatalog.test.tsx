import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Knowledge } from './Knowledge';
const fixture = vi.hoisted(() => ({ state: 'normal', calls: [] as string[] }));
vi.mock('../lib/store', () => ({
  useApp: () => ({ ready: true, scope: {}, canKnowledge: false }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useList: (path: string) => {
    fixture.calls.push(path);
    return {
      items:
        fixture.state === 'normal'
          ? [
              {
                id: 'r1',
                knowledge_id: 'k1',
                revision: 2,
                kind: 'runbook',
                state: 'published',
                visibility: 'common',
                content: {
                  title: 'Memory runbook',
                  description: 'Original description',
                  search: { codes: ['xid:92'] },
                  classification: { domain: 'GPU_MEMORY' },
                },
              },
            ]
          : [],
      isPending: false,
      isError: fixture.state === 'error',
      error: new Error('Unavailable'),
      refetch: vi.fn(),
      hasNextPage: false,
      isFetching: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
      data: { pages: [] },
    };
  },
}));
beforeEach(() => {
  fixture.state = 'normal';
  fixture.calls = [];
});
it('defaults to published revisions, keeps descriptions and adds categories to existing cards', () => {
  const html = renderToStaticMarkup(<Knowledge />);
  expect(fixture.calls.every((p) => p.includes('state=published'))).toBe(true);
  expect(html).toContain('Runbook 현황');
  expect(html).toContain('Original description');
  expect(html).toContain('revision 2');
  expect(html).toContain('runbook-card-footer');
  expect(html).not.toContain('분류 선택 해제');
});
it('does not replace failed or absent catalogs with zero counts', () => {
  fixture.state = 'error';
  expect(renderToStaticMarkup(<Knowledge />)).toContain('데이터를 가져오지 못했습니다.');
  fixture.state = 'empty';
  const html = renderToStaticMarkup(<Knowledge />);
  expect(html).toContain('발행된 Runbook이 없습니다.');
  expect(html).toContain('조건에 맞는 지식이 없습니다.');
  expect(html).not.toContain('runbook-categories');
});
