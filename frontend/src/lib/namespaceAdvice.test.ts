import { expect, it } from 'vitest';
import { adviceGroups, advicePresentation, adviceTime } from './namespaceAdvice';

it('groups nonadjacent advice by exact cluster and Namespace without changing selection', () => {
  const input = [
    { fact_id: 'a', target: { cluster_id: 'cpc-2', namespace: 'service' } },
    { fact_id: 'b', target: { cluster_id: 'cpc-1', namespace: 'batch' } },
    { fact_id: 'c', target: { cluster_id: 'cpc-1', namespace: 'research' } },
    { fact_id: 'd', target: { cluster_id: 'cpc-1', namespace: 'batch' } },
    { fact_id: 'e', target: { cluster_id: 'cpc-2', namespace: 'batch' } },
  ];
  const original = JSON.stringify(input);
  const groups = adviceGroups(input);
  expect(groups.map((g) => g.cluster)).toEqual(['cpc-1', 'cpc-2']);
  expect(groups[0].namespaces.map((n) => n.namespace)).toEqual(['batch', 'research']);
  expect(groups[0].namespaces[0].items.map((i) => i.fact_id)).toEqual(['b', 'd']);
  expect(groups.flatMap((g) => g.namespaces.flatMap((n) => n.items))).toHaveLength(5);
  expect(JSON.stringify(input)).toBe(original);
  expect(adviceGroups([{}, {}])).toHaveLength(2);
  expect(
    adviceGroups([{ target: { cluster_id: 'x' } }, { target: { cluster_id: 'x' } }])[0].namespaces,
  ).toHaveLength(2);
});

it('labels each advice type and never invents a comparison or a continuous observation', () => {
  const kinds = [
    'capacity_review',
    'schedule_candidate',
    'relative_activity',
    'queue_review',
    'batch_progress',
    'resident_memory',
    'repeated_activity',
  ];
  expect(new Set(kinds.map((kind) => advicePresentation({ kind }).title)).size).toBe(7);
  expect(advicePresentation({ kind: 'relative_activity' }).windows.map((w) => w.label)).toEqual([
    '비교 구간',
    '낮은 활동 구간',
  ]);
  expect(advicePresentation({ kind: 'schedule_candidate' }).windows.map((w) => w.label)).toEqual([
    '낮은 활동 구간',
  ]);
  const periods = [
    { start: '2026-10-22T00:00:00Z', end: '2026-10-22T01:00:00Z' },
    { start: '2026-10-22T03:00:00Z', end: '2026-10-22T04:00:00Z' },
  ];
  expect(
    advicePresentation({ kind: 'repeated_activity', observed_periods: periods }).windows.map(
      (w) => w.period,
    ),
  ).toEqual(periods);
  expect(advicePresentation({ kind: 'repeated_activity' }).windows[0].label).toContain(
    '연속 관측 아님',
  );
  expect(advicePresentation({ kind: 'unknown' }).title).toBe('운영 점검');
});

it('renders KST, preserves date boundaries and rejects unknown or reversed windows', () => {
  expect(adviceTime({ start: '2026-10-22T11:00:00Z', end: '2026-10-22T15:00:00Z' })).toBe(
    '2026. 10. 22. 20:00 ~ 2026. 10. 23. 00:00 KST',
  );
  expect(adviceTime({ start: '2026-10-22T09:00:09+09:00', end: '2026-10-22T10:00:17+09:00' })).toBe(
    '2026. 10. 22. 09:00:09 ~ 10:00:17 KST',
  );
  for (const period of [
    {},
    { start: 'bad', end: 'bad' },
    { start: '2026-10-22T00:00:00', end: '2026-10-22T01:00:00' },
    { start: '2026-10-22T01:00:00Z', end: '2026-10-22T00:00:00Z' },
  ])
    expect(adviceTime(period)).toBe('시간 범위 미확인');
});

it('sorts named targets before unknowns and keeps inner advice in stored order', () => {
  const input = [
    { fact_id: 'c2', target: { cluster_id: 'cpc-2', namespace: 'zebra' } },
    { fact_id: 'z-first', target: { cluster_id: 'cpc-1', namespace: 'zebra' } },
    { fact_id: 'alpha', target: { cluster_id: 'cpc-1', namespace: 'alpha' } },
    { fact_id: 'a-last', target: { cluster_id: 'cpc-1', namespace: 'zebra' } },
    { fact_id: 'unknown-ns', target: { cluster_id: 'cpc-1' } },
    { fact_id: 'unknown-cluster', target: {} },
  ];
  const before = JSON.stringify(input);
  const groups = adviceGroups(input);
  expect(groups.map((g) => g.cluster)).toEqual(['cpc-1', 'cpc-2', '']);
  expect(groups[0].namespaces.map((n) => n.namespace)).toEqual(['alpha', 'zebra', '']);
  expect(groups[0].namespaces[1].items.map((i) => i.fact_id)).toEqual(['z-first', 'a-last']);
  expect(JSON.stringify(input)).toBe(before);
});
