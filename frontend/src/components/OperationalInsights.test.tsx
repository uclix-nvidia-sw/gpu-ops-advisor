import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { type Row } from '../lib/live';
import { HourlyOverview, OperationalInsights, operationalEvidence } from './OperationalInsights';
import { IncidentBreakdown } from './Console2Charts';

const start = '2026-10-28T15:00:00Z';
const end = '2026-10-28T17:00:00Z';
const hour = (offset: number, value: number | null) => ({
  start: new Date(Date.parse(start) + offset * 3600000).toISOString(),
  end: new Date(Date.parse(start) + (offset + 1) * 3600000).toISOString(),
  sample_count: 240,
  activity_percent: value,
});
const row = (name: string, overrides: Row = {}) => ({
  cluster_id: 'cpc-1',
  namespace: name,
  gpu_model: 'A100',
  activity_percent: 0,
  expected_hours: 2,
  comparison_status: 'insufficient_observation',
  hours: [hour(0, 0), hour(1, 0)],
  gpu_memory: {
    hours: [0, 1].map((i) => ({ ...hour(i, 0), used_gib_per_gpu: 90, free_gib_per_gpu: 10 })),
  },
  ...overrides,
});
const report = (records: Row[]) => ({
  time_range: { start, end },
  topics: [{ topic_id: 'namespace_usage', rows: records }],
  narrative: [
    {
      topic_id: 'namespace_usage',
      selection: {
        criteria: { low_activity_percent: 5, high_memory_percent: 80, high_activity_percent: 80 },
      },
    },
  ],
});

it('pairs only the same complete hours and preserves measured zero without changing stored data', () => {
  const value = report([row('service')]);
  const saved = JSON.stringify(value);
  const [e] = operationalEvidence(value);
  expect(e.overlap).toHaveLength(2);
  expect(e.paired[0].memory).toBe(90);
  const html = renderToStaticMarkup(<HourlyOverview value={value} />);
  expect(html).toContain('활동률 0.00% · 메모리 90.00%');
  expect(html).toContain('2/2개 동시 관측 시간대');
  expect(html).toContain('비교 보류');
  expect(JSON.stringify(value)).toBe(saved);
});

it('does not infer overlap from daily averages, missing samples, shifted hours or duplicates', () => {
  for (const overrides of [
    { hours: [hour(0, null), hour(1, null)] },
    { hours: [{ ...hour(0, 0), sample_count: 0 }] },
    { hours: [hour(0, 0), hour(0, 0)] },
    {
      hours: [hour(0, 0)],
      gpu_memory: { hours: [{ ...hour(1, 0), used_gib_per_gpu: 90, free_gib_per_gpu: 10 }] },
    },
    { gpu_memory: { used_gib_per_gpu: 90, free_gib_per_gpu: 10 } },
  ])
    expect(operationalEvidence(report([row('a', overrides)]))[0].overlap).toHaveLength(0);
  const unknown = renderToStaticMarkup(
    <HourlyOverview value={report([row('a', { activity_percent: null, hours: [] })])} />,
  );
  expect(unknown).toContain('활동률 미확인');
  expect(unknown).not.toContain('활동률 0.00%');
});

it('keeps models and clusters separate, rejects outside-period bins and uses saved thresholds', () => {
  const value = report([
    row('a'),
    row('a', { cluster_id: 'cpc-2', gpu_model: 'H100', hours: [hour(-1, 99), hour(2, 99)] }),
  ]);
  const evidence = operationalEvidence(value);
  expect(new Set(evidence.map((e) => e.key)).size).toBe(2);
  expect(evidence[1].hours).toHaveLength(0);
  expect(operationalEvidence({ ...value, narrative: [] })[0].overlap).toHaveLength(0);
});

it('surfaces a valid hourly peak and conditional next checks, never a capacity verdict', () => {
  const value = report([
    row('batch', { activity_percent: 45, hours: [hour(0, 0), hour(1, 90)] }),
    row('missing', { activity_percent: null, hours: [] }),
  ]);
  const html = renderToStaticMarkup(<OperationalInsights value={value} />);
  expect(html).toContain('45.00%');
  expect(html).toContain('90.00%');
  expect(html).toContain('일부 판단 보류');
  expect(html).toContain('마감·메모리 요구');
  expect(html).not.toContain('회수 가능합니다');
  const noCriteria = renderToStaticMarkup(
    <OperationalInsights value={{ ...value, narrative: [] }} />,
  );
  expect(noCriteria).not.toContain('기간 평균과 시간대 평균 최고');
});

it('ranks absolute category changes, excludes unknown comparisons and deduplicates incident IDs', () => {
  const html = renderToStaticMarkup(
    <IncidentBreakdown
      summary={{
        categories: [
          { cluster_id: 'c1', name: 'XID 48', count: 4, previous_count: 6 },
          { cluster_id: 'c1', name: 'XID 52', count: 3, previous_count: 0 },
          { cluster_id: 'c1', name: 'unknown', count: 99, previous_count: null },
        ],
        incidents: [
          { id: 'a', cluster_id: 'c1', target: { node: 'n1' } },
          { id: 'a', cluster_id: 'c1', target: { node: 'n1' } },
        ],
      }}
    />,
  );
  expect(html.indexOf('XID 52')).toBeLessThan(html.indexOf('XID 48'));
  expect(html).toContain('+3건');
  expect(html).toContain('-2건');
  expect(html).not.toContain('unknown');
  expect(html).toContain('저장된 사건 내역 1건');
});
