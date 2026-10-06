import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { JobDetail } from './Jobs';
import type { Row } from '../lib/live';
const fixture = vi.hoisted(() => ({ job: {} as Row, error: false }));
vi.mock('../lib/store', () => ({ useApp: () => ({ mode: 'classic', canOperate: true }) }));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: () => ({
    data: fixture.job,
    isPending: false,
    isError: fixture.error,
    error: new Error('fixture offline'),
    refetch: vi.fn(),
  }),
  useCommand: () => ({ run: vi.fn(), busy: false, error: '', setError: vi.fn() }),
}));
beforeEach(() => {
  fixture.error = false;
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
