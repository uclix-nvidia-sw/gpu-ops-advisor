import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import {
  ConsoleWorkspace,
  DebugRunList,
  OperatorIncidentList,
  OperatorReportList,
} from './ConsoleWorkspace';
import type { ReactNode } from 'react';
import type { Row } from '../lib/live';
const state = vi.hoisted(() => ({ mode: 'control', paths: [] as string[], error: false }));
vi.mock('../lib/store', () => ({
  useApp: () => ({
    mode: state.mode,
    canOperate: true,
    scope: { clusters: [{ cluster_id: 'c1', namespaces: null }] },
    timeRange: { start: '2026-10-21T00:00:00Z', end: '2026-10-22T00:00:00Z' },
  }),
}));
vi.mock('../lib/live', async (original) => ({
  ...(await original<typeof import('../lib/live')>()),
  useResource: () => ({ data: undefined, isPending: false, isError: false }),
  useList: (path: string | null) => {
    if (path) state.paths.push(path);
    return {
      items: [],
      isPending: false,
      isError: state.error,
      error: new Error('fixture network error'),
      refetch: vi.fn(),
    };
  },
}));
const render = (child: ReactNode, path = '/dashboard') =>
  renderToStaticMarkup(<MemoryRouter initialEntries={[path]}>{child}</MemoryRouter>);
beforeEach(() => {
  state.mode = 'control';
  state.paths = [];
  state.error = false;
});

it('uses separate latest execution and last published RCA without fetching every incident', () => {
  const html = render(
    <OperatorIncidentList
      from="/cases?status=open"
      items={[
        {
          id: 'i1',
          title: 'GPU fault',
          state: 'open',
          rca_summary: {
            latest_job: { job_id: 'j2', status: 'running' },
            latest_published: { job_id: 'j1', result_status: 'partial' },
          },
        },
      ]}
    />,
  );
  expect(html).toContain('최근 조사 · 실행 중');
  expect(html).toContain('발행 결과');
  expect(html).toContain('부분 산출');
  expect(html).toContain('/incidents/i1?analysis=j1');
  expect(html).toContain('/incidents/i1#new-incident-state');
  expect(state.paths).toEqual([]);
});
it('keeps missing publication unknown and never turns successful execution into a report', () => {
  const html = render(
    <OperatorIncidentList
      from="/cases"
      items={[
        { id: 'i1', title: 'Unknown' },
        { id: 'i2', rca_summary: { latest_job: { job_id: 'j2', status: 'succeeded' } } },
      ]}
    />,
  );
  expect(html).toContain('발행 여부 미확인');
  expect(html).toContain('발행된 RCA 없음');
  expect(html).not.toContain('RCA 확인·처리');
});
it('offers progress and deletion history instead of reading unpublished or removed reports', () => {
  const items: Row[] = [
    { id: 'pending', status: 'running', result: { summary: 'PRIVATE_CANDIDATE' } },
    { id: 'deleted', status: 'succeeded', result_ref: 'old', deletion: { status: 'complete' } },
  ];
  const html = render(<OperatorReportList from="/reports" items={items} />);
  expect(html).toContain('작성 현황');
  expect(html).toContain('삭제 기록');
  expect(html).not.toContain('보고서 읽기');
  expect(html).not.toContain('PRIVATE_CANDIDATE');
});
it('keeps debug destination and list filters together and labels Ops by report scope', () => {
  const html = render(
    <DebugRunList
      from="/jobs?status=failed"
      items={[
        {
          id: 'job/1',
          kind: 'report',
          scope: { clusters: [{ cluster_id: 'c1', namespaces: ['ns'] }] },
          status: 'failed',
        },
      ]}
    />,
  );
  expect(html).toContain('/jobs/job%2F1?tab=execution&amp;from=%2Fjobs%3Fstatus%3Dfailed');
  expect(html).toContain('c1');
  expect(html).toContain('결과 미발행');
  expect(html).not.toContain('알람 이름 미확인');
});
it('keeps old unclosed incidents in the default queue regardless of the global time range', () => {
  render(<ConsoleWorkspace />);
  const incidents = new URL(state.paths[0], 'http://fixture'),
    reports = new URL(state.paths[1], 'http://fixture');
  expect(incidents.pathname).toBe('/incidents');
  expect(incidents.searchParams.has('from')).toBe(false);
  expect(incidents.searchParams.has('to')).toBe(false);
  expect(incidents.searchParams.get('status')).toBe('unclosed');
  expect(reports.pathname).toBe('/reports');
  expect(reports.searchParams.has('from')).toBe(false);
});
it('uses server side execution filters without applying the incident time filter to jobs', () => {
  state.mode = 'workbench';
  const html = render(<ConsoleWorkspace />, '/jobs?status=failed&kind=rca');
  const url = new URL(state.paths[0], 'http://fixture');
  expect(url.searchParams.get('status')).toBe('failed');
  expect(url.searchParams.get('kind')).toBe('rca');
  expect(url.searchParams.has('from')).toBe(false);
  expect(html).toContain('aria-label="실행 상태"');
  expect(html).toContain('/settings/backend');
});
it('displays network failure instead of an empty or healthy queue', () => {
  state.error = true;
  const html = render(<ConsoleWorkspace />);
  expect(html).toContain('데이터를 가져오지 못했습니다.');
  expect(html).not.toContain('조회된 미종결 사건이 없습니다.');
});
it('does not send a developer execution filter as an incident lifecycle status on mode change', () => {
  render(<ConsoleWorkspace />, '/dashboard?status=failed');
  expect(new URL(state.paths[0], 'http://fixture').searchParams.get('status')).toBe('unclosed');
  state.paths = [];
  render(<ConsoleWorkspace />, '/cases?status=running');
  expect(new URL(state.paths[0], 'http://fixture').searchParams.get('status')).toBe('unclosed');
});

it('queries full history separately and applies optional occurrence dates in KST', () => {
  render(<ConsoleWorkspace />, '/cases?status=all&occurred_from=2026-10-01&occurred_to=2026-10-02');
  const q = new URL(state.paths[0], 'http://fixture').searchParams;
  expect(q.has('status')).toBe(false);
  expect(q.get('from')).toBe('2026-09-30T15:00:00.000Z');
  expect(q.get('to')).toBe('2026-10-02T15:00:00.000Z');
});
it('never limits unclosed incidents by leftover occurrence filters, even invalid ones', () => {
  const html = render(
    <ConsoleWorkspace />,
    '/cases?status=unclosed&occurred_from=wrong&occurred_to=2026-10-01',
  );
  const q = new URL(state.paths[0], 'http://fixture').searchParams;
  expect(q.get('status')).toBe('unclosed');
  expect(q.has('from')).toBe(false);
  expect(q.has('to')).toBe(false);
  expect(html).not.toContain('올바른 발생일');
  expect(html).not.toContain('보고서 만들기');
});
it('finds stored jobs by node and incident with an independent receipt window', () => {
  state.mode = 'workbench';
  render(
    <ConsoleWorkspace />,
    '/jobs?node=dgx-07&incident_id=i1&received_from=2026-10-01&received_to=2026-10-01',
  );
  const q = new URL(state.paths[0], 'http://fixture').searchParams;
  expect(q.get('node')).toBe('dgx-07');
  expect(q.get('incident_id')).toBe('i1');
  expect(q.get('from')).toBe('2026-09-30T15:00:00.000Z');
  expect(q.get('to')).toBe('2026-10-01T15:00:00.000Z');
});
it('distinguishes failure diagnosis from full job history', () => {
  state.mode = 'workbench';
  render(<ConsoleWorkspace />);
  expect(new URL(state.paths[0], 'http://fixture').searchParams.get('status')).toBe('failed');
  state.paths = [];
  render(<ConsoleWorkspace />, '/jobs');
  expect(new URL(state.paths[0], 'http://fixture').searchParams.has('status')).toBe(false);
});
it('shows stored termination reasons without claiming a reason for missing records', () => {
  const html = render(
    <DebugRunList
      from="/jobs"
      items={[
        { id: 'failed', stage: 'synthesis', termination_reason: 'llm_http_error' },
        { id: 'unknown' },
      ]}
    />,
  );
  expect(html).toContain('모델 서버가 HTTP 오류를 반환했습니다.');
  expect(html).toContain('synthesis');
  expect(html).toContain('종료 사유 미기록');
});
it('searches reports by analysis dates independently of receipt dates', () => {
  render(
    <ConsoleWorkspace />,
    '/reports?analysis_from=2026-10-01&analysis_to=2026-10-01&received_from=2026-10-07',
  );
  const q = new URL(state.paths[0], 'http://fixture').searchParams;
  expect(q.get('analysis_from')).toBe('2026-09-30T15:00:00.000Z');
  expect(q.get('analysis_to')).toBe('2026-10-01T15:00:00.000Z');
  expect(q.get('from')).toBe('2026-10-06T15:00:00.000Z');
});
it('blocks malformed analysis date searches instead of fetching all reports', () => {
  const html = render(<ConsoleWorkspace />, '/reports?analysis_from=wrong');
  expect(state.paths).toEqual([]);
  expect(html).toContain('올바른 분석일을 선택해 주세요.');
});
it('shows only published bounded previews and keeps missing summaries explicit', () => {
  const preview = {
    summaries: [{ topic_id: 'namespace_usage', text: '활동률이 5%p 감소했습니다.' }],
    limitations: ['일부 시간대 자료 누락'],
    truncated: true,
  };
  const html = render(
    <OperatorReportList
      from="/reports"
      items={[
        { id: 'a', result_ref: 'r', report_preview: preview },
        { id: 'b', report_preview: { summaries: [{ text: 'UNPUBLISHED' }] } },
        { id: 'c', result_ref: 'r' },
        {
          id: 'd',
          result_ref: 'r',
          deletion: {},
          report_preview: { summaries: [{ text: 'DELETED' }] },
        },
      ]}
    />,
  );
  expect(html).toContain('활동률이 5%p 감소했습니다.');
  expect(html).toContain('일부 시간대 자료 누락');
  expect(html).toContain('요약 일부만 표시');
  expect(html).toContain('목록 요약 없음');
  expect(html).not.toContain('UNPUBLISHED');
  expect(html).not.toContain('DELETED');
});
it('does not interpret an empty incident list as healthy hardware', () => {
  const html = render(<ConsoleWorkspace />, '/cases');
  expect(html).toContain('장비 정상 여부를 판단할 수 없습니다.');
  expect(state.paths).toHaveLength(1);
});
it('labels a preview as AI interpretation only when the stored narrative is complete', () => {
  const renderPreview = (narrative_status: string) =>
    render(
      <OperatorReportList
        from="/reports"
        items={[
          {
            id: 'a',
            result_ref: 'r',
            report_preview: {
              method: 'llm_interpreted',
              narrative_status,
              summaries: [{ text: '저장된 변화' }],
            },
          },
        ]}
      />,
    );
  expect(renderPreview('complete')).toContain('AI');
  expect(renderPreview('failed')).not.toContain('AI');
  expect(renderPreview('')).not.toContain('AI');
});
