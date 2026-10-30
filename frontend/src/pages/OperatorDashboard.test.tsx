import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { incidentViews } from '../lib/incidentOverview';
import { OperatorDashboard } from './OperatorDashboard';

vi.mock('../components/OpsUsage', () => ({
  OpsUsage: () => <section>preserved-ops-usage</section>,
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: () => ({ data: { items: [] } }),
}));
vi.mock('../components/IncidentOverview', async (original) => ({
  ...(await original<typeof import('../components/IncidentOverview')>()),
  useRecentIncidents: () => ({
    query: { isPending: false, isError: false },
    now: new Date('2026-10-28T00:00:00Z'),
    truncated: false,
    views: incidentViews([
      {
        id: 'old-firing',
        occurred_at: '2026-10-24T00:00:00Z',
        alarm_status: 'firing',
        target: { node: 'gpu-1', title: 'XID 79 on PCI:0000:01:00.0' },
        rca_summary: { latest_published: { job_id: 'report', result_status: 'ready' } },
      },
      { id: 'resolved', occurred_at: '2026-10-25T00:00:00Z', alarm_status: 'resolved' },
      { id: 'unknown', occurred_at: '2026-10-26T00:00:00Z', alarm_status: null },
    ]),
  }),
}));

it('counts recorded incidents without receipt-state filters', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <OperatorDashboard />
    </MemoryRouter>,
  );
  expect(html).not.toContain('focus=firing');
  expect(html).toContain('<strong>3</strong>');
  expect(html).not.toContain('focus=resolved');
  expect(html).toContain('href="/analyses/report#final-report"');
  expect(html).toContain('현재 장애 지속·복구 여부를 판단하지 않습니다');
  expect(html).not.toContain('지금 발생 중');
  expect(html).not.toContain('확인 필요');
  expect(html).not.toContain('해제 신호 없음');
  expect(html.indexOf('preserved-ops-usage')).toBeLessThan(html.indexOf('class="oh-kpis"'));
  expect(html).toContain('oh-received-incidents');
  expect(html).toContain('aria-controls="received-incidents"');
  expect(html).toContain('/cases?period=14');
});
