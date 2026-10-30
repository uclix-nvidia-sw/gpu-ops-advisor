import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import {
  Console2,
  IncidentTable,
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
it('filters published quality without inferring current health from legacy alarm receipt', () => {
  expect(console2Filter(incidents, new URLSearchParams('quality=limited'))).toHaveLength(5);
  expect(console2Filter(incidents, new URLSearchParams('quality=blocked'))).toHaveLength(1);
  expect(
    console2Filter(incidents, new URLSearchParams('focus=resolved&quality=ready')),
  ).toHaveLength(1);
  expect(console2Filter(incidents, new URLSearchParams('focus=firing&quality=ready'))).toHaveLength(
    1,
  );
});
it('shows visual comparisons before details, preserves visible interpretations and keeps classic presentation unchanged', () => {
  const value = {
    narrative_status: 'complete',
    quality: { report: { method: 'llm_interpreted' } },
    topics: [
      { topic_id: 'namespace_usage', status: 'partial', rows: [] },
      { topic_id: 'incident_summary', status: 'ready', rows: [], summary: { count: 0 } },
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
  expect(modern.indexOf('기간 내 사건 비교')).toBeLessThan(
    modern.indexOf('id="namespace-summary-title"'),
  );
  expect(modern).toContain('추가 할당 가능 여부 미확인');
  expect(modern).toContain('현재 기간 0건, 이전 기간 미확인건');
  expect(modern).toContain('XID 48 수신');
  expect(modern).not.toContain('c2-saved-interpretation');
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

it('preserves all execution states alongside a previous published partial report', () => {
  const states = ['queued', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled', 'expired'];
  const views = incidentViews(
    states.map((status, i) => ({
      id: String(i),
      occurred_at: `2026-10-29T0${i}:00:00Z`,
      target: { title: `SXID ${100 + i} PCI:0000:c5:00.0`, cluster_id: 'a', k8s_node_name: 'node' },
      rca_summary: {
        latest_job: { job_id: 'new-' + i, status },
        latest_published: { job_id: 'old-' + i, result_status: 'partial' },
      },
    })),
  );
  for (const execution of states)
    expect(
      console2Filter(views, new URLSearchParams({ execution, quality: 'partial' })),
    ).toHaveLength(1);
  expect(console2Filter(views, new URLSearchParams('kind=gpu'))).toHaveLength(0);
  expect(console2Filter(views, new URLSearchParams('kind=switch&code=sxid%3A100'))).toHaveLength(1);
  expect(console2Filter(views, new URLSearchParams('sort=oldest'))[0].id).toBe('0');
  expect(console2Filter(views, new URLSearchParams('sort=error'))[0].code).toBe('sxid:100');
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <IncidentTable views={views} />
    </MemoryRouter>,
  );
  for (const label of [
    '실행 대기',
    '실행 중',
    '재시도 대기',
    '실행 완료',
    '실행 실패',
    '취소 완료',
    '기한 만료',
    '부분 산출',
    '이전 발행 보고서',
  ])
    expect(html).toContain(label);
  expect(html).not.toContain('알림 수신');
  expect(html).toContain('/analyses/old-0');
  expect(html).toContain('/incidents/0');
});

it('separates received identity from guidance and escapes untrusted alert text', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <IncidentTable
        views={incidentViews([
          {
            id: 'raw',
            occurred_at: '2026-10-29T01:00:00Z',
            target: {
              title: 'XID 103 <script>alert(1)</script> detected on GPU PCI:0000:bd:00',
              k8s_node_name: 'dgx02',
            },
          },
        ])}
      />
    </MemoryRouter>,
  );
  expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
  expect(html).not.toContain('NVJPG5 Error');
  expect(html).toContain('PCI 0000:bd:00');
  expect(html).toContain('클러스터 미확인');
  expect(html).toContain('실행 기록 없음');
  expect(html).toContain('aria-expanded="false"');
  expect(html).toContain('<th>런북 참고</th>');
});
