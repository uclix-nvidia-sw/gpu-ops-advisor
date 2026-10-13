import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { AggregateReport } from './AggregateReport';
import { aggregatePeriod } from '../pages/AggregateReportForm';

it('renders observed zero separately from missing observations and comparison', () => {
  const row = {
    cluster_id: 'cpc-1',
    namespace: 'test-dept-service',
    gpu_model: 'A100',
    activity_percent: 0,
    previous_activity_percent: null,
    change_percentage_points: null,
    valid_hours: 1,
    expected_hours: 24,
    low_activity_hours: null,
    hours: [
      {
        start: '2026-10-11T15:00:00Z',
        end: '2026-10-11T16:00:00Z',
        activity_percent: 0,
        reasons: [],
      },
      {
        start: '2026-10-11T16:00:00Z',
        end: '2026-10-11T17:00:00Z',
        activity_percent: null,
        reasons: ['unobserved_hour'],
      },
    ],
  };
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{ topics: [{ topic_id: 'namespace_usage', rows: [row], findings: [] }] }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('0.00%');
  expect(html).toContain('산출 불가');
  expect(html).toContain('비교 보류');
  expect(html).toContain('이 시간대 관측 없음');
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain('role="img"');
});
it('keeps an empty incident period distinct from hardware health', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <AggregateReport
        value={{
          topics: [
            { topic_id: 'incident_summary', summary: { count: 0, incidents: [], groups: [] } },
          ],
        }}
        onEvidence={() => {}}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('저장된 사건이 없습니다');
  expect(html).toContain('장비 전체의 무장애를 뜻하지 않습니다');
});
it('builds complete KST days across month boundaries', () => {
  expect(aggregatePeriod('2026-10-02', 'weekly')).toEqual({
    start: '2026-09-25T15:00:00.000Z',
    end: '2026-10-02T15:00:00.000Z',
  });
  expect(aggregatePeriod('2026-10-02', 'daily')).toEqual({
    start: '2026-10-01T15:00:00.000Z',
    end: '2026-10-02T15:00:00.000Z',
  });
});
