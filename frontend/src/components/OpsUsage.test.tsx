import { expect, it } from 'vitest';
import { opsUsage, snapshotReports } from './OpsUsage';

// Shape of a stored report-aggregate-v1 result (namespace_usage rows and workloads).
const result = {
  topics: [
    {
      topic_id: 'incident_summary',
      summary: { count: 11, previous_count: 0 },
    },
    {
      topic_id: 'namespace_usage',
      rows: [
        { cluster_id: 'cpc-1', namespace: '', gpu_model: 'A100-40GB', activity_percent: null },
        {
          cluster_id: 'cpc-1',
          namespace: 'forecast',
          gpu_model: 'A100-40GB',
          activity_percent: 59.15,
          previous_activity_percent: 39.6,
          observed_gpu_count: 3,
          hours: [
            { start: '2026-10-25T16:00:00Z', activity_percent: 42 },
            { start: '2026-10-25T15:00:00Z', activity_percent: 26 },
          ],
        },
        {
          cluster_id: 'cpc-1',
          namespace: 'runai',
          gpu_model: 'A100-40GB',
          activity_percent: null,
          observed_gpu_count: 4,
          hours: [{ start: '2026-10-25T15:00:00Z', activity_percent: null }],
        },
        {
          cluster_id: 'cpc-2',
          namespace: 'runai',
          gpu_model: 'V100',
          activity_percent: 0,
          observed_gpu_count: 1,
        },
      ],
      workloads: [
        {
          cluster_id: 'cpc-1',
          namespace: 'forecast',
          hours: [{ pending_peak: 22 }, { pending_peak: 18 }],
        },
        { cluster_id: 'cpc-1', namespace: 'runai', hours: [] },
      ],
    },
  ],
};

it('reads Namespace rows, keeps missing activity apart from 0% and takes the pending peak', () => {
  const { items, hours, alerts } = opsUsage(result);
  expect(items.map((u) => u.label)).toEqual([
    'forecast',
    'runai (cpc-1 · A100-40GB)',
    'runai (cpc-2 · V100)',
  ]);
  const [forecast, runai, cpc2] = items;
  expect(forecast).toMatchObject({ activity: 59.15, previous: 39.6, gpus: 3, pending: 22 });
  expect(forecast.hourly['2026-10-25T15:00:00Z']).toBe(26);
  expect(runai.activity).toBeNull();
  expect(runai.pending).toBeNull();
  expect(cpc2.activity).toBe(0);
  expect(hours).toEqual(['2026-10-25T15:00:00Z', '2026-10-25T16:00:00Z']);
  expect(alerts).toEqual({ count: 11, previous: 0 });
});

it('returns nothing to chart for a report without Namespace usage', () => {
  expect(opsUsage({ topics: [{ topic_id: 'incident_summary', summary: {} }] })).toEqual({
    items: [],
    hours: [],
    alerts: null,
  });
  expect(opsUsage({}).items).toEqual([]);
});

it('omits incomparable prior activity only from the Console2 snapshot', () => {
  expect(opsUsage(result, true).items[0].previous).toBeNull();
  expect(opsUsage(result).items[0].previous).toBe(39.6);
  const comparable = structuredClone(result);
  Object.assign(comparable.topics[1].rows![1], { comparison_status: 'comparable' });
  expect(opsUsage(comparable, true).items[0].previous).toBe(39.6);
});

it('selects published snapshots by analysis end, excluding deleted and unpublished reports', () => {
  const report = {
    status: 'succeeded',
    result_ref: 'stored',
    topic_ids: ['namespace_usage'],
    result_status: 'partial',
  };
  const items = [
    {
      ...report,
      id: 'recently-generated-old-period',
      time_range: { end: '2026-10-22T00:00:00Z' },
      created_at: '2026-10-29T00:00:00Z',
    },
    { ...report, id: 'newer-analysis', time_range: { end: '2026-10-28T00:00:00Z' } },
    { ...report, id: 'deleted', deletion: { at: 'today' } },
    { ...report, id: 'unpublished', result_ref: '' },
    { ...report, id: 'running', status: 'running' },
  ];
  expect(snapshotReports(items).map((r) => r.id)).toEqual([
    'newer-analysis',
    'recently-generated-old-period',
  ]);
  expect(snapshotReports(items)[0].result_status).toBe('partial');
  expect(items[0].id).toBe('recently-generated-old-period');
});
