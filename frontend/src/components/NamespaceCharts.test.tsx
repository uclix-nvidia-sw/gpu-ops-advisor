import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  activityPoints,
  memoryPercent,
  NamespaceCharts,
  type NamespaceGroup,
} from './NamespaceCharts';

const start = Date.parse('2026-10-13T00:00:00Z');
const hour = (offset: number, value: unknown) => ({
  start: new Date(start + offset * 3600000).toISOString(),
  end: new Date(start + (offset + 1) * 3600000).toISOString(),
  activity_percent: value,
});
it('aligns timestamps, preserves zero, and never connects gaps or invalid values', () => {
  const points = activityPoints(
    [
      hour(7, 80),
      hour(0, 0),
      hour(1, 20),
      hour(2, null),
      hour(3, 30),
      hour(4, NaN),
      hour(5, 101),
      hour(6, -1),
    ],
    start,
    start + 8 * 3600000,
  );
  expect(points.map((p) => p.move)).toEqual([true, false, true, true]);
  expect(points.map((p) => p.y)).toEqual([220, 184, 166, 76]);
  expect(points[3].x - points[2].x).toBe(438);
  expect(
    activityPoints([hour(0, 10), hour(2, 20)], start, start + 3 * 3600000).map((p) => p.move),
  ).toEqual([true, true]);
  expect(activityPoints([{ activity_percent: 5 }], start, start)).toEqual([]);
});
const group = (cluster: string, namespace: string, models = ['A100', 'V100']): NamespaceGroup => ({
  key: JSON.stringify([cluster, namespace]),
  cluster,
  namespace,
  models: models.map((gpu_model) => ({ gpu_model, hours: [hour(0, 0), hour(1, 50)] })),
});
const groups = [
  group('cpc-1', 'dept-a'),
  group('cpc-1', 'dept-b', ['A100']),
  group('cpc-2', 'dept-a', ['V100']),
];
const render = (hidden = new Set<string>(), data = groups) =>
  renderToStaticMarkup(
    <NamespaceCharts groups={data} hidden={hidden} onToggle={() => {}} onSetCluster={() => {}} />,
  );
it('starts with all cluster/namespace series and shares color but not model stroke', () => {
  const html = render();
  expect(html.indexOf('role="img"')).toBeLessThan(html.indexOf('<fieldset'));
  expect((html.match(/role="img"/g) || []).length).toBe(2);
  expect((html.match(/checked=""/g) || []).length).toBe(3);
  const lines = [
    ...html.matchAll(
      /<g aria-label="([^"]+)"><path[^>]*stroke="([^"]+)"[^>]*stroke-dasharray="([^"]*)"/g,
    ),
  ];
  expect(lines.length).toBe(4);
  expect(lines[0][2]).toBe(lines[1][2]);
  expect(lines[0][3]).not.toBe(lines[1][3]);
  expect(lines[0][2]).not.toBe(lines[2][2]);
  expect(lines[1][2]).toBe(lines[3][2]);
});
it('hides all models of only the selected cluster namespace and distinguishes empty from unavailable', () => {
  const hidden = render(new Set([JSON.stringify(['activity', groups[0].key])]));
  expect(hidden).not.toContain('aria-label="dept-a / A100"');
  expect((hidden.match(/aria-label="dept-a \/ V100"/g) || []).length).toBe(1);
  const allCleared = render(new Set(groups.map((g) => JSON.stringify(['activity', g.key]))));
  expect(allCleared).toContain('선택 없음 · 선과 점 숨김');
  expect((allCleared.match(/role="img"/g) || []).length).toBe(2);
  expect(allCleared).not.toContain('<g aria-label=');
  expect(allCleared).not.toContain('<path');
  expect(allCleared).not.toContain('<circle');
  expect(allCleared).not.toContain('checked=""');
  expect(allCleared).not.toContain('활동률을 계산할 수 있는 시간대가 없습니다');
  expect((allCleared.match(/class="aggregate-grid"/g) || []).length).toBe(6);
  expect(allCleared.match(/<text[^>]*>.*?<\/text>/g)).toEqual(
    render().match(/<text[^>]*>.*?<\/text>/g),
  );
  expect(
    render(new Set(), [{ ...groups[0], models: [{ gpu_model: 'A100', hours: [hour(0, null)] }] }]),
  ).toContain('활동률을 계산할 수 있는 시간대가 없습니다');
});

it('keeps an empty chart safe when the report has no time boundaries', () => {
  const html = render(new Set(), [{ ...groups[0], models: [{ gpu_model: 'A100', hours: [] }] }]);
  expect(html).toContain('활동률을 계산할 수 있는 시간대가 없습니다');
  expect((html.match(/class="aggregate-grid"/g) || []).length).toBe(3);
  expect(html).not.toContain('Invalid Date');
});

it('separates memory units, preserves missing gaps, and keeps axes/selection aligned', () => {
  const memoryHours = [0, 0.5, null, 0.8].map((v, i) => ({
    ...hour(i, 40),
    used_gib_per_gpu: v,
    free_gib_per_gpu: v == null ? null : 16,
  }));
  const points = activityPoints(
    memoryHours,
    start,
    start + 4 * 3600000,
    'used_gib_per_gpu',
    1,
    ' GiB/GPU',
  );
  expect(points.map((p) => p.move)).toEqual([true, false, true]);
  expect(points.map((p) => p.y)).toEqual([220, 130, 76]);
  expect(points[0].label).toContain('0.00 GiB/GPU');
  const data = groups.map((g) => ({
    ...g,
    models: g.models.map((r) => ({ ...r, gpu_memory: { hours: memoryHours } })),
  }));
  const html = render(new Set(), data);
  expect((html.match(/role="img"/g) || []).length).toBe(4);
  expect(html).toContain('GPU 메모리 사용 비율 (%)');
  expect(html).toContain('<h4>cpc-1 클러스터</h4>');
  expect(html).toContain('3.03%');
  expect((html.match(/checked=""/g) || []).length).toBe(6);
  const hidden = render(new Set([JSON.stringify(['activity', groups[0].key])]), data);
  expect((hidden.match(/aria-label="dept-a \/ A100"/g) || []).length).toBe(1);
  expect((hidden.match(/aria-label="dept-a \/ V100"/g) || []).length).toBe(3);
  const empty = render(
    new Set(
      data.flatMap((g) => ['activity', 'memory'].map((metric) => JSON.stringify([metric, g.key]))),
    ),
    data,
  );
  expect(empty).not.toContain('<path');
  expect(empty).not.toContain('<circle');
  expect(empty.match(/<text[^>]*>.*?<\/text>/g)).toEqual(html.match(/<text[^>]*>.*?<\/text>/g));
  const missing = render(new Set(), [
    { ...data[0], models: [{ ...data[0].models[0], gpu_memory: { hours: [] } }] },
  ]);
  expect(missing).toContain('확인된 GPU 메모리 자료가 없습니다');
});

it('derives memory share only from valid used and free observations', () => {
  expect(memoryPercent({ used_gib_per_gpu: 0, free_gib_per_gpu: 80 })).toBe(0);
  expect(memoryPercent({ used_gib_per_gpu: 0, free_gib_per_gpu: 80 }, 'free_gib_per_gpu')).toBe(
    100,
  );
  expect(memoryPercent({ used_gib_per_gpu: 60, free_gib_per_gpu: 20 })).toBe(75);
  for (const [used, free] of [
    [null, 80],
    [8, null],
    [0, 0],
    [-1, 5],
    [NaN, 2],
    [1, Infinity],
  ]) {
    expect(memoryPercent({ used_gib_per_gpu: used, free_gib_per_gpu: free })).toBeNull();
  }
});

it('links reader selections across both metrics and replaces unavailable plots with an explanation', () => {
  const data: NamespaceGroup[] = [
    group('cpc-1', 'dept-a', ['A100']),
    group('cpc-2', 'dept-a', ['A100']),
  ].map((g) => ({
    ...g,
    models: g.models.map((m) => ({
      ...m,
      gpu_memory: { hours: [{ ...hour(0, 0), used_gib_per_gpu: 0, free_gib_per_gpu: 80 }] },
    })),
  }));
  const renderReader = (hidden: Set<string>, items = data) =>
    renderToStaticMarkup(
      <NamespaceCharts
        reader
        groups={items}
        hidden={hidden}
        onToggle={() => {}}
        onSetCluster={() => {}}
      />,
    );
  const selected = renderReader(new Set());
  expect((selected.match(/checked=""/g) || []).length).toBe(2);
  expect(selected).toContain('0.00%');
  const hidden = renderReader(new Set([JSON.stringify(['both', data[0].key])]));
  expect((hidden.match(/checked=""/g) || []).length).toBe(1);
  expect((hidden.match(/<g aria-label="dept-a \/ A100"/g) || []).length).toBe(2);
  const missing = renderReader(new Set(), [
    { ...data[0], models: [{ gpu_model: 'A100', hours: [], gpu_memory: { hours: [] } }] },
  ]);
  expect(missing).toContain('활동률·메모리를 비교할 유효 관측이 없습니다');
  expect(missing).toContain('#c2-observation-coverage');
  expect(missing).not.toContain('role="img"');
});
