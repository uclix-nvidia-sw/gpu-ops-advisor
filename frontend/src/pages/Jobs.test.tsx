import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { JobDetail, Jobs, JobHistoryTable } from './Jobs';
import type { Row } from '../lib/live';
const fixture = vi.hoisted(() => ({
  job: {} as Row,
  error: false,
  items: [] as Row[],
  paths: [] as string[],
}));
vi.mock('../lib/store', () => ({
  useApp: () => ({ mode: 'classic', canOperate: true, ready: true, scope: { clusters: [] } }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: () => ({
    data: fixture.job,
    isPending: false,
    isError: fixture.error,
    error: new Error('fixture offline'),
    refetch: vi.fn(),
  }),
  useList: (path: string) => {
    fixture.paths.push(path);
    return {
      items: fixture.items,
      isPending: false,
      isError: fixture.error,
      error: new Error('fixture offline'),
      refetch: vi.fn(),
      hasNextPage: false,
      dataUpdatedAt: 0,
    };
  },
  useCommand: () => ({ run: vi.fn(), busy: false, error: '', setError: vi.fn() }),
}));
beforeEach(() => {
  fixture.error = false;
  fixture.items = [];
  fixture.paths = [];
  fixture.job = {
    kind: 'report',
    status: 'retry_wait',
    result_status: 'unpublished',
    attempt_no: 2,
    stage: 'saving',
    topic_ids: ['O08', 'O09'],
    group_by: ['cluster'],
    topic_group_by: { O08: ['namespace'], O09: ['cluster'] },
    attempts: [
      {
        attempt_no: 1,
        started_at: '2026-10-06T00:00:00Z',
        ended_at: '2026-10-06T00:03:00Z',
        stage: 'saving',
        termination_reason: 'timeout',
      },
      {
        attempt_no: 2,
        started_at: '2026-10-06T00:04:00Z',
        ended_at: '2026-10-06T00:07:00Z',
        stage: 'workflow',
        termination_reason: 'dependency_unavailable',
      },
    ],
  };
});
function render() {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/jobs/j1']}>
      <Routes>
        <Route path="/jobs/:id" element={<JobDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}
it('places recorded attempts beside execution context before named analysis topics', () => {
  const html = render();
  expect(html).toContain('실행 상태와 시도 이력');
  expect(html).toContain('GPU 운영 보고서 · 2개 주제</h1>');
  expect(html).toContain('작업 ID · j1');
  expect(html).toContain('재시도 대기');
  expect(html.indexOf('2차<small>')).toBeLessThan(html.indexOf('1차</th>'));
  expect(html.indexOf('aria-label="시도 이력"')).toBeLessThan(html.indexOf('분석 대상과 주제'));
  for (const text of [
    '시간 초과',
    '연결 서비스 사용 불가',
    '2026. 10. 06. 09:00:00',
    'Namespace·프로젝트 배분',
    'GPU 에너지',
    'Namespace',
    '클러스터',
  ])
    expect(html).toContain(text);
  expect(html).not.toContain('저장된 결과 보기');
  expect(fixture.job.attempts).toMatchObject([{ attempt_no: 1 }, { attempt_no: 2 }]);
});
it('keeps missing records unknown and distinguishes an unstarted job', () => {
  fixture.job = { ...fixture.job, status: 'queued', attempt_no: 0, attempts: [], topic_ids: [] };
  expect(render()).toContain('아직 실행을 시작하지 않아 시도 이력이 없습니다.');
  expect(render()).toContain('분석 주제 미확인');
  delete fixture.job.attempts;
  expect(render()).toContain('시도 이력 미확인');
});
it('does not infer a successful attempt from a missing termination reason', () => {
  fixture.job = {
    ...fixture.job,
    status: 'failed',
    attempts: [{ attempt_no: 2, stage: 'unrecognized', ended_at: null }],
    topic_ids: ['X01'],
    topic_group_by: {},
  };
  const html = render();
  expect(html).toContain('종료 기록 없음');
  expect(html).toContain('unrecognized');
  expect(html).toContain('X01');
  expect(html).not.toContain('장비·Node 변화');
  expect(html).not.toContain('실행 완료');
});
it.each(['report', 'rca'])('shows released execution with unconfirmed inference for %s', (kind) => {
  fixture.job = {
    ...fixture.job,
    kind,
    status: 'failed',
    attempts: [
      {
        attempt_no: 1,
        ended_at: '2026-10-06T00:03:00Z',
        termination_reason: 'timeout',
        remote_call_state: 'unknown',
        slot_state: 'released',
        slot_released_at: '2026-10-06T00:03:00Z',
      },
    ],
  };
  for (const remote_call_state of ['unknown', 'running']) {
    (fixture.job.attempts as Row[])[0].remote_call_state = remote_call_state;
    const html = render();
    expect(html).toContain('종료된 1차 시도의 실행 자리는 반환됐습니다.');
    expect(html).toContain('모델 서버의 추론 종료 여부는 미확인입니다.');
    expect(html).toContain('해당 시도의 늦은 결과는 발행하지 않습니다.');
    expect(html).not.toContain('저장된 결과 보기');
  }
});
it.each([
  {},
  { slot_state: 'released', remote_call_state: null },
  { slot_state: 'released', remote_call_state: 'terminated' },
  { slot_state: 'released', remote_call_state: 'not_started' },
  { slot_state: 'quarantined', remote_call_state: 'unknown' },
  { slot_state: 'active', remote_call_state: 'running' },
  { slot_state: 'released', remote_call_state: 'unknown', ended_at: null },
])('does not infer released unconfirmed inference from other or missing states %j', (state) => {
  fixture.job.attempts = [{ attempt_no: 1, ended_at: '2026-10-06T00:03:00Z', ...state }];
  expect(render()).not.toContain('실행 자리는 반환됐습니다.');
});
it('keeps publication quality separate from successful execution', () => {
  fixture.job = {
    ...fixture.job,
    status: 'succeeded',
    result_status: 'blocked',
    result_ref: 'result-1',
  };
  const html = render();
  expect(html).toContain('실행 완료');
  expect(html).toContain('근거 부족');
  expect(html).toContain('/reports/j1#final-report');
  fixture.error = true;
  expect(render()).toContain('fixture offline');
  expect(render()).not.toContain('실행 상태와 시도 이력');
});

const listMarkup = (items: Row[]) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/jobs?status=succeeded']}>
      <JobHistoryTable items={items} />
    </MemoryRouter>,
  );
it('opens published results from titles and keeps explicit job links', () => {
  const items = [
    {
      ...fixture.job,
      id: 'complete',
      status: 'succeeded',
      result_status: 'partial',
      result_ref: 'r1',
      created_at: '2026-10-06T00:00:00Z',
      scope: {
        clusters: [
          { cluster_id: 'c1', namespaces: null },
          { cluster_id: 'c2', namespaces: null },
        ],
      },
    },
    { ...fixture.job, id: 'pending', result_ref: null },
    {
      id: 'rca1',
      kind: 'rca',
      status: 'succeeded',
      result_ref: 'r2',
      target: {
        reason: 'GPU temperature',
        cluster_id: 'c1',
        namespace: 'inference',
        node: 'gpu-node-1',
      },
    },
  ];
  const html = listMarkup(items);
  expect(html).toMatch(/class="text-link jobs-title" href="\/reports\/complete#final-report"/);
  expect(html).toContain('href="/jobs/pending"');
  expect(html).toContain('href="/jobs/rca1"');
  expect(html).toContain('href="/reports/complete#final-report"');
  expect(html).toContain('href="/analyses/rca1#final-report"');
  expect(html).toContain('class="text-link jobs-title" href="/reports/pending#final-report"');
  expect(html).toContain('클러스터 2개 · 전체 Namespace');
  expect(html).toContain(
    '<details class="jobs-request-details"><summary>대상·요청 조건 보기</summary>',
  );
  expect(html).not.toContain('<details class="jobs-request-details" open');
  expect(html).toContain('2026. 10. 06.\n09:00:00');
  expect(html).toContain('실행 완료');
  expect(html).toContain('부분 산출');
  expect(html.match(/>결과 보기<\/a>/g)).toHaveLength(2);
  expect(html).toContain('클러스터 c1 · Namespace inference');
  expect(html).toContain('<strong>GPU temperature</strong></span></a>');
  expect(html).toContain('노드: gpu-node-1');
  expect(html.indexOf('/jobs/complete')).toBeLessThan(html.indexOf('/jobs/pending'));
});
it('preserves unknown and empty namespace scope instead of claiming all namespaces', () => {
  for (const scope of [
    undefined,
    { clusters: [{ cluster_id: 'c1' }] },
    { clusters: [{ cluster_id: 'c1', namespaces: [] }] },
  ]) {
    const html = listMarkup([{ ...fixture.job, id: 'unknown', scope }]);
    expect(html).not.toContain('전체 Namespace');
    expect(html).toMatch(/미확인|선택된 Namespace 없음/);
  }
});
it('uses Korean filter labels while keeping status codes in the query', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter initialEntries={['/jobs?kind=report&status=retry_wait']}>
      <Jobs />
    </MemoryRouter>,
  );
  expect(html).toContain('>재시도 대기</option>');
  expect(html).not.toContain('>retry_wait</option>');
  expect(html).toContain('필터 초기화');
  expect(html).toContain('조건에 맞는 작업');
  const url = new URL(fixture.paths.at(-1)!, 'http://localhost');
  expect(url.searchParams.get('status')).toBe('retry_wait');
  expect(url.searchParams.get('kind')).toBe('report');
});
it('distinguishes no matching jobs from a failed list request', () => {
  const renderList = () =>
    renderToStaticMarkup(
      <MemoryRouter initialEntries={['/jobs']}>
        <Jobs />
      </MemoryRouter>,
    );
  expect(renderList()).toContain('조건에 맞는 작업이 없습니다.');
  expect(renderList()).not.toContain('저장된 결과가 없습니다.');
  fixture.error = true;
  expect(renderList()).toContain('fixture offline');
  expect(renderList()).not.toContain('조건에 맞는 작업이 없습니다.');
});

it('keeps missing RCA targets unknown and does not assign a report creation source', () => {
  const html = listMarkup([{ id: 'missing-rca', kind: 'rca', status: 'failed', result_ref: null }]);
  expect(html).toContain('알람 이름 미확인');
  expect(html).toContain('클러스터 미확인 · Namespace 미확인');
  expect(html).toContain('실행 실패');
  expect(html).not.toContain('직접 요청');
  expect(html).not.toContain('자동 생성');
  expect(html).not.toContain('결과 보기</a>');
});
