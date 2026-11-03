import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { incidentViews } from '../lib/incidentOverview';
import {
  IncidentCharts,
  ReportGpuComparison,
  ReportIncidentComparison,
  reportChartRows,
} from './Console2Charts';

it('keeps measured zero, missing values and separate cluster/model rows distinct', () => {
  const value = {
    topics: [
      {
        topic_id: 'namespace_usage',
        rows: [
          {
            cluster_id: 'a',
            namespace: 'train',
            gpu_model: 'A100',
            activity_percent: 0,
            previous_activity_percent: 50,
            comparison_status: 'comparable',
            gpu_memory: { used_gib_per_gpu: 36, free_gib_per_gpu: 4 },
          },
          {
            cluster_id: 'b',
            namespace: 'train',
            gpu_model: 'A100',
            activity_percent: null,
            previous_activity_percent: 80,
            comparison_status: 'previous_not_observed',
          },
          {
            cluster_id: 'a',
            namespace: 'train',
            gpu_model: 'H100',
            activity_percent: 101,
            gpu_memory: { used_gib_per_gpu: 2, free_gib_per_gpu: -1 },
          },
          { cluster_id: 'a', activity_percent: 90 },
        ],
      },
    ],
  };
  const before = JSON.stringify(value);
  const records = reportChartRows(value);
  expect(records).toHaveLength(3);
  expect(new Set(records.map((r) => r.key)).size).toBe(3);
  expect(records.map((r) => [r.activity, r.memory, r.previous])).toEqual([
    [0, 90, 50],
    [null, null, null],
    [null, null, null],
  ]);
  const html = renderToStaticMarkup(<ReportGpuComparison value={value} />);
  expect(html).toContain('활동률 0.00% · 이전 기간 50.00%');
  expect(html).toContain('메모리 사용 비율 90.00%');
  expect(html).toContain('수치 미확인 2개');
  expect(html).not.toContain('이전 기간과 사건 건수 비교');
  expect(JSON.stringify(value)).toBe(before);
});

it('shows unknown instead of a fabricated zero or period delta', () => {
  const value = {
    topics: [{ topic_id: 'incident_summary', summary: { count: 0, previous_count: null } }],
  };
  const html = renderToStaticMarkup(<ReportIncidentComparison value={value} />);
  expect(html).toContain('현재 기간 0건, 이전 기간 미확인건');
  expect(html).toContain('이전 기간 비교 미확인');
  expect(html).not.toContain('네임스페이스별 기간 평균');
  expect(html).not.toMatch(/NaN|Infinity/);
  expect(renderToStaticMarkup(<ReportGpuComparison value={{ topics: [] }} />)).toBe('');
  expect(renderToStaticMarkup(<ReportIncidentComparison value={{ topics: [] }} />)).toBe('');
});

it('compares stored incident counts without converting them to current fault status', () => {
  const html = renderToStaticMarkup(
    <ReportIncidentComparison
      value={{
        topics: [{ topic_id: 'incident_summary', summary: { count: 180, previous_count: 78 } }],
      }}
    />,
  );
  expect(html).toContain('이전 기간 대비 +102건');
  expect(html).toContain('현재 기간 180건, 이전 기간 78건');
  expect(html).toContain('현재 장애가 진행 중인 장비 수를 뜻하지는 않습니다.');
});

it('plots KST daily totals and links each date and category to the matching case filter', () => {
  const views = incidentViews([
    { id: '1', occurred_at: '2026-10-28T15:01:00Z', target: { title: 'XID 48' } },
    { id: '2', occurred_at: '2026-10-29T03:00:00Z', target: { title: 'SXID 15001' } },
  ]);
  const render = (items = views) =>
    renderToStaticMarkup(
      <MemoryRouter>
        <IncidentCharts views={items} days={['2026-10-28', '2026-10-29']} period="7" />
      </MemoryRouter>,
    );
  const html = render();
  expect(html).toContain('2026.10.29. (목) 사건 2건');
  expect(html).toContain('2026.10.28. (수) 사건 0건');
  expect(html).toContain('/cases?from=2026-10-29&amp;to=2026-10-29');
  expect(html).toContain('/cases?period=7&amp;category=link');
  expect(html).toContain('GPU 자체 1건, GPU 간 연결 1건');
  expect(render([])).not.toMatch(/NaN|Infinity|pathLength="100"/);
});

it('groups display rows by cluster, namespace and model without changing saved order or values', () => {
  const records = [
    { cluster_id: 'cpc-2', namespace: 'same', gpu_model: 'A100', activity_percent: 20 },
    { cluster_id: 'cpc-1', namespace: 'z', gpu_model: 'A100', activity_percent: 30 },
    { cluster_id: 'cpc-1', namespace: 'same', gpu_model: 'H100', activity_percent: 40 },
    { cluster_id: 'cpc-1', namespace: 'same', gpu_model: 'A100', activity_percent: 50 },
  ];
  const value = { topics: [{ topic_id: 'namespace_usage', rows: records }] };
  const saved = JSON.stringify(value);
  expect(reportChartRows(value).map((row) => row.activity)).toEqual([50, 40, 30, 20]);
  const html = renderToStaticMarkup(<ReportGpuComparison value={value} />);
  expect(html.indexOf('aria-label="cpc-1 GPU 사용 관측"')).toBeLessThan(
    html.indexOf('aria-label="cpc-2 GPU 사용 관측"'),
  );
  expect(html.match(/class="c2-comparison-row"/g)).toHaveLength(4);
  expect(JSON.stringify(value)).toBe(saved);
});
