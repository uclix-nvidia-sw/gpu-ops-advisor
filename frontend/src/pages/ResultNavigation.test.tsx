import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ResultPage } from './Results';
import { Cases } from './Cases';
import { JobRows } from '../components/live';
import type { Row } from '../lib/live';
const fixture = vi.hoisted(() => ({
  mode: 'classic',
  paths: [] as (string | null)[],
  job: {} as Row,
}));
vi.mock('../lib/store', () => ({
  useApp: () => ({ mode: fixture.mode, ready: true, canOperate: true, scope: { clusters: [] } }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: (path: string | null) => {
    fixture.paths.push(path);
    return { data: fixture.job, isPending: false, isError: false };
  },
  useList: (path: string | null) => {
    fixture.paths.push(path);
    return { items: [], isPending: false, isError: false };
  },
  useCommand: () => ({ run: vi.fn(), busy: false, error: '' }),
}));
beforeEach(() => {
  fixture.paths = [];
  fixture.job = {
    id: 'saved',
    status: 'succeeded',
    result_ref: 'candidate',
    result_status: 'partial',
    result: {
      result_status: 'partial',
      summary: '저장된 분석 내용',
      topics: [],
      evidence_refs: [],
    },
  };
});
it.each(['classic', 'operations', 'developer'])(
  'reads published results in %s without redirecting to jobs',
  (mode) => {
    fixture.mode = mode;
    for (const kind of ['analysis', 'report']) {
      const route = kind === 'analysis' ? '/analyses' : '/reports';
      const html = renderToStaticMarkup(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter initialEntries={[route + '/saved#final-report']}>
            <Routes>
              <Route path={route + '/:id'} element={<ResultPage kind={kind} />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(fixture.paths).toContain(route + '/saved');
      expect(html).toContain('저장된 결과');
      expect(html).toContain('작업 상태·시도 이력');
      expect(html).toContain('href="/jobs/saved"');
      expect(html).not.toContain('작업 디버깅');
    }
  },
);
it('keeps developer RCA lists on the RCA menu', () => {
  fixture.mode = 'developer';
  const html = renderToStaticMarkup(
    <MemoryRouter initialEntries={['/cases?tab=reports']}>
      <Cases />
    </MemoryRouter>,
  );
  expect(fixture.paths.some((path) => path?.startsWith('/analyses?'))).toBe(true);
  expect(html).toContain('RCA 조사 목록');
  expect(html).not.toContain('공개된 RCA 보고서');
  expect(fixture.paths.some((path) => path?.includes('status=succeeded'))).toBe(true);
});

it('starts the RCA menu with investigations while preserving explicit incident navigation', () => {
  for (const [url, path] of [
    ['/cases', '/analyses?'],
    ['/cases?tab=incidents', '/incidents?'],
  ]) {
    fixture.paths = [];
    renderToStaticMarkup(
      <MemoryRouter initialEntries={[url]}>
        <Cases />
      </MemoryRouter>,
    );
    expect(fixture.paths.some((p) => p?.startsWith(path))).toBe(true);
  }
});

it.each(['queued', 'retry_wait', 'failed', 'cancelled'])(
  'keeps an unpublished %s report on its own page with request context',
  (status) => {
    fixture.mode = 'classic';
    fixture.job = {
      ...fixture.job,
      status,
      result_ref: null,
      queue_reason: status === 'retry_wait' ? 'inference_quarantined' : null,
      topic_ids: ['O08'],
      scope: { clusters: [{ cluster_id: 'example-cluster', namespaces: null }] },
      time_range: { start: '2026-10-05T00:00:00Z', end: '2026-10-06T00:00:00Z' },
    };
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/reports/saved#final-report']}>
          <Routes>
            <Route path="/reports/:id" element={<ResultPage kind="report" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(fixture.paths).toContain('/reports/saved');
    expect(html).toContain('아직 발행된 보고서가 없습니다');
    expect(html).toContain('example-cluster');
    expect(html).toContain('요청한 분석 주제');
    expect(html).toContain('id="final-report"');
    expect(html).not.toContain('저장된 분석 내용');
    expect(html).toContain('href="/jobs/saved"');
    if (status === 'retry_wait') expect(html).toContain('이전 추론의 종료 확인');
  },
);

it.each(['classic', 'operations', 'developer'])(
  'shows a deleted report and cleanup state without publishing or rerun actions in %s',
  (mode) => {
    fixture.mode = mode;
    fixture.job = {
      ...fixture.job,
      kind: 'report',
      result_ref: null,
      result_status: 'deleted',
      deletion: {
        deleted_at: '2026-10-12T00:00:00Z',
        reason: '오래된 보고서 정리',
        evidence_count: 9,
        artifact_cleanup_state: 'pending',
      },
    };
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/reports/saved']}>
        <Routes>
          <Route path="/reports/:id" element={<ResultPage kind="report" />} />
        </Routes>
      </MemoryRouter>,
    );
    for (const text of [
      '삭제된 보고서입니다',
      '오래된 보고서 정리',
      '정리 대기',
      'href="/jobs/saved"',
    ])
      expect(html).toContain(text);
    for (const text of [
      '아직 발행된 보고서',
      '새 조건으로 보고서 요청',
      'HTML 다운로드',
      'CSV 다운로드',
      '원본 결과 보기',
      '저장된 분석 내용',
    ])
      expect(html).not.toContain(text);
  },
);

it.each(['', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled', 'expired'])(
  'uses server-side status filtering in the unified RCA list: %s',
  (status) => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/cases?tab=analyses&status=' + status]}>
        <Cases />
      </MemoryRouter>,
    );
    expect(html).toContain('RCA 조사 목록');
    expect(html).not.toContain('>조사 이력</button>');
    expect(html).not.toContain('>최종 보고서</button>');
    expect(
      fixture.paths.some(
        (path) => path?.startsWith('/analyses?') && (!status || path.includes('status=' + status)),
      ),
    ).toBe(true);
  },
);

it('routes completed RCA titles to results and unfinished investigations to execution', () => {
  const items = [
    {
      id: 'done',
      kind: 'rca',
      status: 'succeeded',
      result_ref: 'published',
      result_status: 'partial',
      target: { node: 'dgx01' },
    },
    { id: 'active', kind: 'rca', status: 'running', result_ref: null },
    { id: 'failed', kind: 'rca', status: 'failed', result_ref: null },
  ];
  const html = renderToStaticMarkup(
    <MemoryRouter initialEntries={['/cases']}>
      <JobRows items={items} />
    </MemoryRouter>,
  );
  expect(html).toContain('/analyses/done#final-report');
  expect(html).toContain('/jobs/active');
  expect(html).toContain('/jobs/failed');
  expect(html).not.toContain('/analyses/active');
  expect(html).not.toContain('<th>종류</th>');
  expect(html).not.toContain('최종 보고서 보기');
  expect(html).toContain('부분 산출');
});
