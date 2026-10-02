import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { JobRows } from './live';
import type { Row } from '../lib/live';

const state = vi.hoisted(() => ({
  data: {} as Row,
  isPending: false,
  isError: false,
  paths: [] as string[],
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: (path: string) => {
    state.paths.push(path);
    return { ...state, refetch: vi.fn() };
  },
}));
const job = {
  id: 'latest',
  kind: 'report',
  result_ref: 'r1',
  status: 'succeeded',
  result_status: 'partial',
  topic_ids: ['O08'],
  group_by: ['namespace'],
};
const render = (items: Row[]) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/reports']}>
      <JobRows items={items} />
    </MemoryRouter>,
  );
beforeEach(() => {
  state.paths = [];
  state.isPending = false;
  state.isError = false;
  state.data = {
    ...job,
    result: {
      topics: [
        {
          topic_id: 'O08',
          status: 'partial',
          missing_inputs: ['shared_gpu_attribution_unverified'],
          metrics: [
            {
              id: 'O08.namespace_connected_gpu_util.0',
              target: { cluster_id: 'c1', namespace: 'inference' },
              value: 0,
              unit: 'percent',
            },
            {
              id: 'O08.namespace_connected_gpu_util.1',
              target: { cluster_id: 'c1', namespace: 'shared' },
              value: null,
              unit: 'percent',
            },
          ],
        },
      ],
    },
  };
});
it('keeps the newest request first even while an older published report exists', () => {
  const html = render([
    {
      ...job,
      id: 'pending',
      status: 'queued',
      result_ref: null,
      queue_reason: 'inference_quarantined',
      created_at: '2026-10-02T02:37:18Z',
      time_range: { start: '2026-09-30T15:00:00Z', end: '2026-10-01T15:00:00Z' },
    },
    job,
    { ...job, id: 'older', result_ref: 'r0' },
  ]);
  expect(state.paths).toEqual([]);
  expect(html.indexOf('id="report-row-pending"')).toBeLessThan(
    html.indexOf('id="report-row-latest"'),
  );
  expect(html).toContain('가장 최근 요청');
  expect(html).toContain('2026. 10. 02. 11:37:18');
  expect(html).toContain('2026. 10. 01. 하루 · 1일(24시간)');
  expect(html).toContain('아직 실행 시작 기록이 없습니다');
  expect(html).toContain('이전 추론의 종료 확인');
  expect(html).toContain('/jobs/pending');
  expect(html).toContain('/reports/older#final-report');
  expect(html).not.toContain('핵심 결과');
});
it('shows a saved summary only when the newest request is published', () => {
  const html = render([job]);
  expect(state.paths).toEqual(['/reports/latest']);
  for (const text of ['0 %', '산출 불가', '자료 부족·주의사항', 'GPU 공유 구간'])
    expect(html).toContain(text);
});
it('keeps the report link and retry available when summary retrieval fails', () => {
  state.isError = true;
  const html = render([job]);
  expect(html).toContain('요약을 불러오지 못했습니다');
  expect(html).toContain('요약 다시 불러오기');
  expect(html).toContain('/reports/latest#final-report');
  expect(html).not.toContain('0 %');
});
it('does not show cached summary numbers for a different result reference', () => {
  state.data.result_ref = 'old-ref';
  const html = render([job]);
  expect(html).toContain('결과 참조가 다릅니다');
  expect(html).not.toContain('0 %');
});
it('shows missing topic records without inventing zero counts', () => {
  state.data.result = {};
  const html = render([job]);
  expect(html).toContain('요약에 사용할 주제별 기록이 없습니다');
  expect(html).not.toContain('산출 완료 0');
});

it('shows origin badges on both large and small cards without KST suffixes', () => {
  const html = render([
    { ...job, report_origin: 'schedule' },
    { ...job, id: 'manual', report_origin: 'manual' },
    { ...job, id: 'old' },
  ]);
  expect(html).toContain('생성 방식: 자동 생성');
  expect(html).toContain('생성 방식: 직접 요청');
  expect(html).toContain('생성 방식 미확인');
  expect(html).not.toContain('(KST)');
});
