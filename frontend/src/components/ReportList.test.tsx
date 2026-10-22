import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { JobRows } from './live';
import type { Row } from '../lib/live';

const state = vi.hoisted(() => ({ paths: [] as string[] }));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: (path: string) => {
    state.paths.push(path);
    return { data: {}, isPending: false, isError: false, refetch: vi.fn() };
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
  scope: { clusters: [{ cluster_id: 'cpc-2', namespaces: ['training'] }] },
  time_range: { start: '2026-09-30T15:00:00Z', end: '2026-10-01T15:00:00Z' },
  created_at: '2026-10-02T02:37:18Z',
};
const render = (items: Row[]) =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={['/reports']}>
      <JobRows items={items} />
    </MemoryRouter>,
  );
beforeEach(() => {
  state.paths = [];
});
it('lists reports in the RCA table layout without fetching any report detail', () => {
  const html = render([
    { ...job, id: 'pending', status: 'queued', result_ref: null, result_status: 'unpublished' },
    job,
    { ...job, id: 'older', result_ref: 'r0' },
  ]);
  expect(state.paths).toEqual([]);
  expect(html).toContain('<th>보고서 · 대상</th>');
  expect(html).toContain('<th>실행 기록</th>');
  expect(html).not.toContain('<th>종류</th>');
  expect(html).not.toContain('<th>최종 보고서</th>');
  expect(html.indexOf('id="report-row-pending"')).toBeLessThan(
    html.indexOf('id="report-row-latest"'),
  );
  expect(html).toContain(
    'class="text-link report-history-title" href="/reports/pending#final-report"',
  );
  expect(html).toContain('href="/reports/older#final-report"');
  expect(html).toContain('href="/jobs/pending"');
  expect(html).toContain('2026. 10. 01. · Namespace별 GPU 사용 분석');
  expect(html).toContain('클러스터: <strong>cpc-2</strong> / training');
  expect(html).toContain('2026. 10. 01. 하루 · 1일(24시간)');
  expect(html).toContain('2026. 10. 02.');
  expect(html).toContain('11:37:18');
  expect(html).not.toContain('report-history-card');
  expect(html).not.toContain('현재 목록의 최근 요청');
  expect(html).not.toContain('보고서 요약');
});
it('shows origin badges without KST suffixes and offers deletion only where permitted', () => {
  const html = render([
    { ...job, report_origin: 'schedule', can_delete: true, version: 2 },
    { ...job, id: 'manual', report_origin: 'manual' },
    {
      ...job,
      id: 'gone',
      result_ref: null,
      result_status: 'deleted',
      deletion: { deleted_at: '2026-10-12T00:00:00Z' },
    },
  ]);
  expect(html).toContain('생성 방식: 자동 생성');
  expect(html).toContain('생성 방식: 직접 요청');
  expect(html).not.toContain('(KST)');
  expect(html.match(/>보고서 삭제<\/button>/g)).toHaveLength(1);
  expect(html).toContain('href="/reports/gone#final-report"');
  expect(html).toContain('href="/jobs/gone"');
});
