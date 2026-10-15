import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { WorkloadCharts } from './WorkloadCharts';
describe('WorkloadCharts', () => {
  it('keeps count and elapsed units distinct and includes earlier jobs', () => {
    const html = renderToStaticMarkup(
      <WorkloadCharts
        workloads={[
          {
            cluster_id: 'cpc-2',
            namespace: 'forecast',
            hours: [
              { start: '2026-10-15T04:00:00Z', end: '2026-10-15T05:00:00Z', pending_peak: 2 },
              { start: '2026-10-15T05:00:00Z', end: '2026-10-15T06:00:00Z', pending_peak: 0 },
            ],
            completed_jobs: [
              {
                job_name: 'previous-run',
                started_at: '2026-10-14T01:00:00Z',
                completed_at: '2026-10-15T02:00:00Z',
                elapsed_seconds: 90000,
              },
              {
                job_name: 'smoke-1',
                started_at: '2026-10-15T04:09:21Z',
                completed_at: '2026-10-15T04:29:30Z',
                elapsed_seconds: 1209,
              },
            ],
          },
        ]}
      />,
    );
    expect(html).toContain('최대 대기 2개');
    expect(html).toContain('최대 대기 0개');
    expect(html).toContain('forecast</strong> · 최대 2개');
    expect(html).toContain('<details class="aggregate-workload-detail">');
    expect(html).toContain('<summary>Namespace별 모든 시간대 보기</summary>');
    expect(html).toContain('20분 9초');
    expect(html).toContain('previous-run');
    expect(html).toContain('대기·준비 포함');
  });
  it('shows only the three largest pending namespaces before details', () => {
    const html = renderToStaticMarkup(
      <WorkloadCharts
        workloads={[1, 4, 2, 3].map((peak) => ({
          cluster_id: 'cpc-2',
          namespace: `namespace-${peak}`,
          hours: [
            { start: '2026-10-15T04:00:00Z', end: '2026-10-15T05:00:00Z', pending_peak: peak },
          ],
          completed_jobs: [],
        }))}
      />,
    );
    const highlights = html.split('<details class="aggregate-workload-detail">')[0];
    expect(highlights).toContain('namespace-4</strong>');
    expect(highlights).toContain('namespace-3</strong>');
    expect(highlights).toContain('namespace-2</strong>');
    expect(highlights).not.toContain('namespace-1</strong>');
    expect(highlights).toContain('그 외 1개 Namespace는 상세 보기');
    expect(html).toContain('namespace-1</h6>');
  });
  it('does not turn missing observations into zeros', () => {
    const html = renderToStaticMarkup(
      <WorkloadCharts
        workloads={[{ cluster_id: 'cpc-2', namespace: 'unknown', hours: [], completed_jobs: [] }]}
      />,
    );
    expect(html).toContain('대기 자료 없음');
    expect(html).toContain('대기 관측 자료가 없습니다.');
    expect(html).toContain('확인된 완료 표본 없음');
    expect(html).not.toContain('최대 대기 0개');
  });
});
