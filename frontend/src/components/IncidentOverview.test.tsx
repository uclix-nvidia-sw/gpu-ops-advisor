import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { IncidentRow } from './IncidentOverview';
import { incidentViews } from '../lib/incidentOverview';

const now = new Date('2026-10-26T07:10:00Z');
const base = {
  alarm_status: 'resolved',
  alarm_resolved_at: '2026-10-26T04:27:00Z',
  target: {
    k8s_node_name: 'dgx02',
    title: 'SXID 11001(ingress invalid command) detected on PCI:0000:c8:00.0',
  },
};
const render = (records: Record<string, unknown>[]) => {
  const [v] = incidentViews(records, now);
  return renderToStaticMarkup(
    <MemoryRouter>
      <IncidentRow v={v} now={now} />
    </MemoryRouter>,
  );
};

it('shows the error, device repeat, alert state, NVIDIA action and the report link', () => {
  const html = render([
    { ...base, id: 'old', occurred_at: '2026-10-20T01:00:00Z' },
    {
      ...base,
      id: 'new',
      occurred_at: '2026-10-26T02:07:00Z',
      rca_summary: { latest_published: { job_id: 'job-1', result_status: 'partial' } },
    },
  ]);
  expect(html).toContain('<span class="oh-badge sx">SXID 11001</span>');
  expect(html).toContain('dgx02 · NVSwitch');
  expect(html).toContain('0000:c8:00.0');
  expect(html).toContain('이 스위치 2번째');
  expect(html).toContain('해제됨');
  // Resolve time with the date and weekday in KST.
  expect(html).toContain('2026.10.26. (월) 13:27');
  expect(html).toContain('치명 가능 SXID (FM 표 23)');
  expect(html).toContain('href="/analyses/job-1#final-report"');
  expect(html).toContain('보고서 열기');
  // Result quality labels stay in the report, not the list.
  expect(html).not.toContain('부분 산출');
  // The title and the report button open the RCA report; neither opens the incident.
  expect(html.match(/href="\/analyses\/job-1#final-report"/g)).toHaveLength(2);
  expect(html).not.toContain('href="/incidents/');
});

it('marks a day-old firing alert for checking and a component by its Korean name', () => {
  const stale = render([
    {
      ...base,
      id: 's',
      occurred_at: '2026-10-23T08:48:00Z',
      alarm_status: 'firing',
      rca_summary: {},
    },
  ]);
  expect(stale).toContain('oh-row stale');
  expect(stale).toContain('확인 필요');
  expect(stale).toContain('<span class="oh-rca none">—</span>');
  const disk = render([
    {
      ...base,
      id: 'd',
      occurred_at: '2026-10-26T02:06:00Z',
      target: {
        k8s_node_name: 'dgx02',
        component: 'disk',
        title: 'filesystem remounted as read-only due to errors',
      },
    },
  ]);
  expect(disk).toContain('dgx02 · 서버');
  expect(disk).toContain('읽기 전용 재마운트');
  expect(disk).not.toContain('disk · ');
  expect(disk).not.toContain('번째');
});
