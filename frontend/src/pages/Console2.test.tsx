import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import {
  Console2,
  console2Date,
  console2DeviceKey,
  console2Filter,
  console2Repeats,
} from './Console2';
import { useRecentIncidents } from '../components/IncidentOverview';
import { incidentViews } from '../lib/incidentOverview';
import { AggregateReport } from '../components/AggregateReport';
import { NamespaceCharts } from '../components/NamespaceCharts';

vi.mock('../components/IncidentOverview', async (original) => ({
  ...(await original<typeof import('../components/IncidentOverview')>()),
  useRecentIncidents: vi.fn(() => ({
    query: { isPending: false, isError: false },
    views: [],
    truncated: false,
  })),
}));

it('opens all recorded incidents by default while retaining explicit dashboard and calendar periods', () => {
  const render = (path: string) =>
    renderToStaticMarkup(
      <MemoryRouter initialEntries={[path]}>
        <Console2 />
      </MemoryRouter>,
    );
  expect(render('/cases')).toContain('aria-pressed="true">전체</button>');
  expect(vi.mocked(useRecentIncidents).mock.lastCall?.[0]).toBeNull();
  render('/cases?period=14');
  expect(vi.mocked(useRecentIncidents).mock.lastCall?.[0]).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  render('/cases?from=2026-01-01&to=2026-01-02');
  expect(vi.mocked(useRecentIncidents).mock.lastCall).toEqual(['2026-01-01', '2026-01-02']);
  render('/cases?period=all');
  expect(vi.mocked(useRecentIncidents).mock.lastCall?.[0]).toBeNull();
});

const incidents = incidentViews(
  Array.from({ length: 6 }, (_, i) => ({
    id: String(i),
    occurred_at: '2026-10-29T01:00:00Z',
    alarm_status: i === 5 ? 'resolved' : 'firing',
    target: {
      cluster_id: i < 3 ? 'cpc-1' : 'cpc-2',
      k8s_node_name: 'dgx01',
      title: 'XID 48 PCI:0000:bd:00.0',
    },
    rca_summary: {
      latest_published: {
        job_id: 'job-' + i,
        result_status: i === 4 ? 'blocked' : i === 5 ? 'ready' : 'partial',
      },
    },
  })),
);
it('ignores malformed, impossible or future dates from shared filter URLs', () => {
  for (const value of [null, '', 'invalid', '2026-02-31', '2026-99-01', '2026-10-30']) {
    expect(console2Date(value, '2026-10-29')).toBe('');
  }
  expect(console2Date('2026-10-29', '2026-10-29')).toBe('2026-10-29');
  expect(console2Date('2024-02-29', '2026-10-29')).toBe('2024-02-29');
});
it('keeps identical node/device names in different clusters separate and filters the displayed Kubernetes name', () => {
  expect(console2Repeats(incidents).map((g) => g.length)).toEqual([3, 3]);
  expect(console2Filter(incidents, new URLSearchParams('q=DGX01'))).toHaveLength(6);
  expect(
    console2Filter(incidents, new URLSearchParams('cluster=cpc-1&node=dgx01&q=xid%2048')),
  ).toHaveLength(3);
  expect(
    console2Filter(incidents, new URLSearchParams({ device2: console2DeviceKey(incidents[0]) })),
  ).toHaveLength(3);
  expect(console2Filter(incidents, new URLSearchParams('q=missing-node'))).toEqual([]);
});
it('keeps alarm state and published quality independent, including the combined partial/blocked overview link', () => {
  expect(console2Filter(incidents, new URLSearchParams('quality=limited'))).toHaveLength(5);
  expect(console2Filter(incidents, new URLSearchParams('quality=blocked'))).toHaveLength(1);
  expect(
    console2Filter(incidents, new URLSearchParams('focus=resolved&quality=ready')),
  ).toHaveLength(1);
  expect(console2Filter(incidents, new URLSearchParams('focus=firing&quality=ready'))).toHaveLength(
    0,
  );
});
it('shows both report topics before details, preserves stored statements and keeps classic presentation unchanged', () => {
  const value = {
    narrative_status: 'complete',
    quality: { report: { method: 'llm_interpreted' } },
    topics: [
      { topic_id: 'namespace_usage', status: 'partial', rows: [] },
      { topic_id: 'incident_summary', status: 'ready', rows: [] },
    ],
    narrative: [
      {
        topic_id: 'namespace_usage',
        observation: '활동률 0%, 메모리 91.8%',
        meaning: '미사용 GPU로 판단할 수 없음',
        next_check: '작업 유형 확인',
        interpretation_limit: '하루 관측만 있음',
        advice: [
          {
            fact_id: 'f1',
            kind: 'resident_memory',
            summary: '메모리 사용 작업 확인',
            observation: '활동률 0%, 메모리 91.8%',
            conditions: '추가 할당 가능 여부 미확인',
            target: { cluster_id: 'cpc-1', namespace: 'test' },
          },
        ],
      },
      {
        topic_id: 'incident_summary',
        observation: 'XID 48 수신',
        meaning: '복구 여부 미확인',
        next_check: 'RCA 확인',
        interpretation_limit: '수신 기록 기준',
      },
    ],
  };
  const before = JSON.stringify(value);
  const render = (reader: boolean) =>
    renderToStaticMarkup(
      <MemoryRouter>
        <AggregateReport value={value} reader={reader} />
      </MemoryRouter>,
    );
  const modern = render(true),
    classic = render(false);
  expect(modern.indexOf('XID 48 수신')).toBeLessThan(
    modern.indexOf('id="namespace-summary-title"'),
  );
  expect(modern).toContain('추가 할당 가능 여부 미확인');
  expect(modern).toContain('이 대상·구간을 그래프에서 확인');
  expect(classic).not.toContain('c2-report-summary');
  expect(classic).not.toContain('이 대상·구간을 그래프에서 확인');
  expect(classic).toContain('aria-label="보고서 목차"');
  expect(JSON.stringify(value)).toBe(before);
});
it('highlights only the selected cluster and time interval without changing plotted values or joining gaps', () => {
  const groups = ['cpc-1', 'cpc-2'].map((cluster) => ({
    key: JSON.stringify([cluster, 'test']),
    cluster,
    namespace: 'test',
    models: [
      {
        gpu_model: 'A100',
        hours: [
          { start: '2026-10-28T00:00:00Z', end: '2026-10-28T01:00:00Z', activity_percent: 0 },
          { start: '2026-10-28T02:00:00Z', end: '2026-10-28T03:00:00Z', activity_percent: 80 },
        ],
      },
    ],
  }));
  const render = (highlight: boolean) =>
    renderToStaticMarkup(
      <NamespaceCharts
        groups={groups}
        hidden={new Set()}
        onToggle={() => {}}
        onSetCluster={() => {}}
        reader
        focus={
          highlight
            ? {
                cluster: 'cpc-1',
                namespace: 'test',
                windows: [{ start: '2026-10-28T00:00:00Z', end: '2026-10-28T01:00:00Z' }],
                origin: 'advice',
              }
            : null
        }
      />,
    );
  const plain = render(false),
    focused = render(true);
  const paths = (html: string) => [...html.matchAll(/<path d="([^"]+)"/g)].map((m) => m[1]);
  expect(paths(focused)).toEqual(paths(plain));
  expect(focused.match(/선택한 관측 구간/g)).toHaveLength(1);
  expect(focused).toContain('opacity="0.18"');
  expect(focused).toContain('읽던 제안으로 돌아가기');
});
