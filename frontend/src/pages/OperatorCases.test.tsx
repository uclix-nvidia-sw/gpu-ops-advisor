import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { OperatorCases } from './OperatorCases';
import { incidentViews } from '../lib/incidentOverview';

const now = new Date('2026-10-27T03:00:00Z');
const fixture = vi.hoisted(() => ({ calls: [] as unknown[][], count: 0, status: 'resolved' }));
vi.mock('../components/IncidentOverview', async (original) => ({
  ...(await original<typeof import('../components/IncidentOverview')>()),
  useRecentIncidents: (...args: unknown[]) => {
    fixture.calls.push(args);
    const records = Array.from({ length: fixture.count }, (_, i) => ({
      id: `i${i}`,
      occurred_at: new Date(now.getTime() - i * 3600_000).toISOString(),
      alarm_status: fixture.status,
      alarm_resolved_at: now.toISOString(),
      target: { k8s_node_name: 'dgx01', title: 'XID 79 detected on PCI:0000:07:00.0' },
      rca_summary: { latest_published: { job_id: `job-${i}`, result_status: 'partial' } },
    }));
    return {
      query: { isPending: false, isError: false, error: null, refetch: vi.fn() },
      views: incidentViews(records),
      now,
      truncated: false,
    };
  },
}));
const render = (search = '') =>
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/cases${search}`]}>
      <OperatorCases />
    </MemoryRouter>,
  );
beforeEach(() => {
  fixture.calls = [];
  fixture.count = 60;
  fixture.status = 'resolved';
});

it('keeps day-old firing records in the main paged list and firing filter', () => {
  fixture.status = 'firing';
  const html = render('?focus=firing&page=2');
  expect(html).toContain('51–60 / 60건');
  expect(html).toContain('href="/analyses/job-55#final-report"');
  expect(html).toContain('발생 알림 수신');
  expect(html).not.toContain('알림이 들어온 장애와 RCA 장애 보고서를 한 줄에서 봅니다');
  expect(html).not.toContain('oh-stale');
  expect(html).not.toContain('확인 필요');
});

it('pages incidents by 50 and links each title to its RCA report', () => {
  const first = render();
  expect(first).toContain('1–50 / 60건');
  expect(first).toContain('href="/analyses/job-0#final-report"');
  expect(first).not.toContain('href="/analyses/job-55#final-report"');
  // Title and report button both open the report.
  expect(first.match(/href="\/analyses\/job-0#final-report"/g)).toHaveLength(2);
  const second = render('?page=2');
  expect(second).toContain('51–60 / 60건');
  expect(second).toContain('href="/analyses/job-55#final-report"');
  expect(second).not.toContain('href="/analyses/job-0#final-report"');
  // Out-of-range pages fall back to the last page.
  expect(render('?page=9')).toContain('51–60 / 60건');
});

it('asks the Backend for the chosen days, a single day, or every incident', () => {
  render();
  expect(fixture.calls.at(-1)).toEqual([null, undefined]);
  render('?period=14');
  expect(fixture.calls.at(-1)?.[0]).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  render('?from=2026-10-13&to=2026-10-20');
  expect(fixture.calls.at(-1)).toEqual(['2026-10-13', '2026-10-20']);
  render('?from=2026-10-20');
  expect(fixture.calls.at(-1)).toEqual(['2026-10-20', '2026-10-20']);
  // A reversed or malformed end keeps the single picked day.
  render('?from=2026-10-20&to=2026-10-01');
  expect(fixture.calls.at(-1)).toEqual(['2026-10-20', '2026-10-20']);
  const all = render('?period=all');
  expect(fixture.calls.at(-1)).toEqual([null, undefined]);
  expect(all).toContain('전체 기간');
  render('?from=wrong');
  expect(fixture.calls.at(-1)?.[1]).toBeUndefined();
});

it('shows the range on the calendar button and keeps the empty state explicit', () => {
  fixture.count = 0;
  const html = render('?from=2026-10-20');
  expect(html).toContain('RCA 조사');
  expect(html).toContain('2026.10.20. (화)');
  expect(html).toContain('조건에 맞는 사건이 없습니다.');
  expect(html).not.toContain('oh-pager');
});
