import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Knowledge, runbookSummary } from './Knowledge';
import type { Row } from '../lib/live';

const fixture = vi.hoisted(() => ({ paths: [] as string[], items: [] as Row[] }));
vi.mock('../lib/store', () => ({
  useApp: () => ({ ready: true, canKnowledge: false, scope: { clusters: [] } }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useList: (path: string | null) => {
    if (path) fixture.paths.push(path);
    return {
      items: fixture.items,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
      data: { pages: [{}] },
    };
  },
}));

const runbook = (
  title: string,
  domain: string,
  category: string,
  codes: string[],
  actions: string[] = [],
): Row => ({
  kind: 'runbook',
  content: {
    title,
    classification: { domain, category },
    search: { codes },
    investigation_only: true,
    operator_guidance: { meaning: 'm' },
    recommendations: actions.map((a) => ({ text: `${a}을 적용한다.` })),
  },
});
const items = [
  runbook('SXID 24007 timeout · NVSwitch 조사', 'GPU_INTERCONNECT', 'nvswitch', ['sxid:24007']),
  runbook('SXID 11012 x · NVSwitch 조사', 'GPU_INTERCONNECT', 'nvswitch', ['sxid:11012']),
  runbook('Xid 79 GPU 연결 끊김 조사', 'GPU_DEVICE', 'gpu_access_loss', ['xid:79'], ['RESTART_BM']),
  runbook(
    'XID 13 Graphics · 애플리케이션 오류 조사',
    'GPU_SOFTWARE',
    'application_fault',
    ['xid:13'],
    ['RESTART_APP'],
  ),
  runbook(
    'XID 31 MMU · 애플리케이션 오류 조사',
    'GPU_SOFTWARE',
    'application_fault',
    ['xid:31'],
    ['RESTART_APP', 'RESET_GPU'],
  ),
  runbook('OS 자원 고갈 보고 조사 (Fleet os)', 'NODE_SYSTEM', 'os_resources', []),
  runbook('디스크 오류 보고 조사 (Fleet disk)', 'NODE_SYSTEM', 'disk_filesystem', []),
  { kind: 'policy', content: { title: 'not a runbook' } },
];
beforeEach(() => {
  fixture.paths = [];
  fixture.items = items;
});

it('counts published runbooks by code family and groups them by stored classification', () => {
  const sum = runbookSummary(items);
  expect(sum).toMatchObject({ total: 7, xid: 3, sxid: 2, other: 2, investigation: 7, guided: 7 });
  const label = (l: string) => sum.groups.find((g) => g.label === l)!;
  expect(label('NVSwitch')).toMatchObject({ domain: 'GPU_INTERCONNECT', count: 2 });
  expect(label('애플리케이션 오류').actions).toEqual([
    ['RESTART_APP', 2],
    ['RESET_GPU', 1],
  ]);
  // Korean particles after an action code still count.
  expect(label('Xid 79 GPU 연결 끊김').actions).toEqual([['RESTART_BM', 1]]);
  // Single-runbook categories in one domain share a row.
  expect(label('OS 자원 고갈 보고, 디스크 오류 보고')).toMatchObject({
    count: 2,
    sources: ['os', 'disk'],
  });
});

it('lists published knowledge first and shows the runbook table', () => {
  const html = renderToStaticMarkup(<Knowledge />);
  expect(html).toContain('<option value="published" selected="">발행됨</option>');
  expect(fixture.paths.every((p) => p.includes('state=published'))).toBe(true);
  expect(html).toContain('발행 Runbook 한눈에 보기');
  expect(html).toContain('GPU 간 연결 (NVLink·NVSwitch)');
  expect(html).toContain('SXID 11012·24007');
  expect(html).toContain('호스트 재시작 1');
  expect(html).toContain('Fleet os·disk');
  expect(html).toContain('모든 Runbook이 조사 전용입니다');
});
