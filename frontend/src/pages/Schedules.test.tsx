import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { ScheduleExecution, Schedules } from './Schedules';
import type { Row } from '../lib/live';

const fixture = vi.hoisted(() => ({ schedule: {} as Row, error: false }));
vi.mock('../lib/store', () => ({ useApp: () => ({ ready: true, scope: { clusters: [] } }) }));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useList: () => ({
    items: [fixture.schedule],
    isPending: false,
    isError: fixture.error,
    error: new Error('조회 실패'),
  }),
}));
afterEach(() => vi.unstubAllGlobals());
beforeEach(() => {
  vi.stubGlobal('location', { pathname: '/schedules' });
  fixture.error = false;
  fixture.schedule = {
    id: 's1',
    enabled: true,
    frequency: 'daily',
    next_run_at: '2026-10-03T00:00:00Z',
    latest_occurrence: null,
  };
});
const occurrence = { scheduled_for: '2026-10-02T00:00:00Z', status: 'accepted', job_id: 'j1' };
const render = (element: React.ReactNode) =>
  renderToStaticMarkup(<MemoryRouter>{element}</MemoryRouter>);

it.each([
  ['queued', 0, '접수됨 · 실행 대기'],
  ['running', 1, '실행 중'],
  ['retry_wait', 1, '재시도 대기'],
  ['succeeded', 1, '실행 완료'],
  ['failed', 1, '실행 실패'],
  ['cancelled', 0, '취소 완료'],
  ['expired', 0, '실행 전 기한 만료'],
  ['expired', 1, '기한 만료'],
])('distinguishes execution state %s (%s attempts)', (status, attempt_no, label) => {
  const html = render(
    <ScheduleExecution occurrence={{ ...occurrence, execution: { status, attempt_no } }} />,
  );
  expect(html).toContain(label);
  expect(html).not.toContain('보고서 보기');
  if (attempt_no === 0) expect(html).toContain('아직 실행 시작 기록 없음');
});
it('shows a timed-out attempt separately from quarantine and formats timestamps in Seoul', () => {
  const html = render(
    <ScheduleExecution
      occurrence={{
        ...occurrence,
        execution: {
          status: 'retry_wait',
          attempt_no: 1,
          started_at: '2026-10-02T00:00:11Z',
          ended_at: '2026-10-02T00:02:51Z',
          attempt_reason: 'timeout',
          queue_reason: 'inference_quarantined',
        },
      }}
    />,
  );
  for (const text of [
    '재시도 대기',
    '1차 시작 10. 02. 09:00',
    '시도 종료 10. 02. 09:02',
    '시간 초과',
    '이전 추론의 종료 확인',
  ])
    expect(html).toContain(text);
  expect(html).not.toContain('(KST)');
});
it.each([
  ['pending', '요청 전달 확인 중'],
  ['accepted', '접수됨 · 실행 상태 미확인'],
  ['failed', '요청 전달 실패'],
  ['missed', '실행 건너뜀'],
])('does not treat occurrence %s as completed', (status, label) => {
  const html = render(<ScheduleExecution occurrence={{ ...occurrence, status }} />);
  expect(html).toContain(label);
  expect(html).not.toContain('실행 완료');
});
it('links only published completed reports', () => {
  const html = render(
    <ScheduleExecution
      occurrence={{ ...occurrence, execution: { status: 'succeeded', result_ref: 'r1' } }}
    />,
  );
  expect(html).toContain('href="/reports/j1#final-report"');
});
it('shows overdue missing requests even when the previous report succeeded', () => {
  fixture.schedule.awaiting_occurrence = true;
  fixture.schedule.latest_occurrence = {
    ...occurrence,
    execution: { status: 'succeeded', result_ref: 'r1' },
  };
  const html = render(<Schedules />);
  expect(html).toContain('예정 시각 지남 · 요청 기록 없음');
  expect(html).toContain('실행 완료');
  expect(html).toContain('href="/schedules/s1#schedule-runs"');
});
it('distinguishes first run, old API and paused schedules', () => {
  expect(render(<Schedules />)).toContain('아직 실행 회차 없음');
  delete fixture.schedule.latest_occurrence;
  expect(render(<Schedules />)).toContain('실행 정보 미확인');
  fixture.schedule.enabled = false;
  expect(render(<Schedules />)).toContain('일시 정지 중');
});
it('displays API errors instead of implying there were no runs', () => {
  fixture.error = true;
  const html = render(<Schedules />);
  expect(html).toContain('조회 실패');
  expect(html).not.toContain('아직 실행 회차 없음');
});
