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
  const [v] = incidentViews(records);
  return renderToStaticMarkup(
    <MemoryRouter>
      <IncidentRow v={v} now={now} />
    </MemoryRouter>,
  );
};

it('shows the alert text, device repeat, reference guidance and the report link', () => {
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
  expect(html).not.toContain('해제 알림 수신');
  // Resolve time with the date and weekday in KST.
  expect(html).not.toContain('2026.10.26. (월) 13:27');
  expect(html).toContain('치명 가능 SXID (FM 표 23)');
  expect(html).toContain('href="/analyses/job-1#final-report"');
  expect(html).toContain('보고서 열기');
  // Result quality labels stay in the report, not the list.
  expect(html).not.toContain('부분 산출');
  // The title and the report button open the RCA report; neither opens the incident.
  expect(html.match(/href="\/analyses\/job-1#final-report"/g)).toHaveLength(2);
  expect(html).not.toContain('href="/incidents/');
});

it('keeps historical receipts as incidents without live receipt badges', () => {
  const stale = render([
    {
      ...base,
      id: 's',
      occurred_at: '2026-10-23T08:48:00Z',
      alarm_status: 'firing',
      rca_summary: {},
    },
  ]);
  expect(stale).not.toContain('oh-row firing');
  expect(stale).not.toContain('oh-row stale');
  expect(stale).not.toContain('발생 알림 수신');
  expect(stale).not.toContain('확인 필요');
  expect(stale).not.toContain('해제 신호 없음');
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
  expect(disk).toContain('filesystem remounted as read-only due to errors');
  expect(disk).not.toContain('disk · ');
  expect(disk).not.toContain('번째');
});

it('does not interpret an absent or unknown alarm state as resolved', () => {
  for (const alarm_status of [null, 'unknown']) {
    const html = render([{ ...base, id: 'unknown', occurred_at: now.toISOString(), alarm_status }]);
    expect(html).not.toContain('알림 상태 미확인');
    expect(html).not.toContain('해제 알림 수신');
    expect(html).not.toContain('발생 알림 수신');
  }
});

it('omits unused labels from the incident title and subtitle', () => {
  const html = render([
    {
      ...base,
      id: 'unused',
      occurred_at: now.toISOString(),
      target: { title: 'XID 6 ROBUST_CHANNEL_FIFO_ERROR_PARSE_ERR detected on GPU' },
    },
  ]);
  expect(html).toContain('ROBUST_CHANNEL_FIFO_ERROR_PARSE_ERR');
  expect(html).not.toMatch(/Unused|미사용/);
});
