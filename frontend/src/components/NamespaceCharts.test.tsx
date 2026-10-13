import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { activityPoints, NamespaceCharts, type NamespaceGroup } from './NamespaceCharts';

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
  const hidden = render(new Set([groups[0].key]));
  expect(hidden).not.toContain('aria-label="dept-a / A100"');
  expect((hidden.match(/aria-label="dept-a \/ V100"/g) || []).length).toBe(1);
  const allCleared = render(new Set(groups.map((g) => g.key)));
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
