import { beforeEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import {
  ConsoleWorkspace,
  DebugRunList,
  OperatorIncidentList,
  OperatorConsole,
  OperatorReportList,
} from './ConsoleWorkspace';
import type { ReactNode } from 'react';
import type { Row } from '../lib/live';
const state = vi.hoisted(() => ({ mode: 'classic', paths: [] as string[], error: false }));
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
  state.mode = 'classic';
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
it.each([false, true])(
  'keeps progress/deletion links and hides unpublished bodies (compact=%s)',
  (compact) => {
    const items: Row[] = [
      { id: 'pending', status: 'running', result: { summary: 'PRIVATE_CANDIDATE' } },
      { id: 'deleted', status: 'succeeded', result_ref: 'old', deletion: { status: 'complete' } },
    ];
    const html = render(<OperatorReportList from="/reports" items={items} compact={compact} />);
    expect(html).toContain('작성 현황');
    expect(html).toContain('삭제 기록');
    expect(html).not.toContain('보고서 읽기');
    expect(html).not.toContain('PRIVATE_CANDIDATE');
  },
);
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
it('displays network failure instead of an empty report list', () => {
  state.error = true;
  const html = render(<ConsoleWorkspace />, '/reports');
  expect(html).toContain('데이터를 가져오지 못했습니다.');
  expect(html).not.toContain('조회된 보고서가 없습니다.');
});
it('keeps classic RCA pages, the former Ops console reports and no job list in the unified console', () => {
  for (const path of ['/dashboard', '/cases', '/analyses/a1', '/incidents/i1', '/jobs/j1'])
    expect(render(<ConsoleWorkspace />, path)).toBe('');
  // The job list redirects to RCA 조사 instead of loading jobs.
  expect(render(<ConsoleWorkspace />, '/jobs')).toBe('');
  expect(state.paths).toEqual([]);
  const html = render(<ConsoleWorkspace />, '/reports');
  expect(html).toContain('Ops 보고서');
  expect(new URL(state.paths[0], 'http://fixture').pathname).toBe('/reports');
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

it('labels partial interpretation previews without claiming all topics succeeded', () => {
  const html = render(
    <OperatorReportList
      from="/reports"
      items={[
        {
          id: 'partial',
          result_ref: 'published',
          report_preview: {
            method: 'partial_interpretation',
            narrative_status: 'failed',
            summaries: [{ text: '채택된 AI 설명과 계산 요약' }],
          },
        },
      ]}
    />,
  );
  expect(html).toContain('일부 주제 AI 해석·계산 요약');
  expect(html).not.toContain('>AI 해석 요약<');
});

it('keeps compact table metadata, publication distinctions and saved preview text without detail reads', () => {
  const items: Row[] = [
    {
      id: 'published',
      status: 'succeeded',
      result_ref: 'r1',
      result_status: 'partial',
      report_origin: 'schedule',
      created_at: '2026-10-23T07:33:35Z',
      scope: { clusters: [{ cluster_id: 'cpc-2', namespaces: ['training-long-namespace'] }] },
      time_range: { start: '2026-10-21T15:00:00Z', end: '2026-10-22T15:00:00Z' },
      report_preview: {
        method: 'deterministic_fallback',
        narrative_status: 'failed',
        summaries: [{ text: '저장 원문: 활동률 25.7%' }],
      },
    },
    { id: 'old', status: 'succeeded' },
  ];
  const saved = JSON.stringify(items);
  const html = render(
    <OperatorReportList compact from="/reports?status=succeeded" items={items} />,
  );
  expect(html).toContain('<table');
  expect(html).toContain('보고서 · 분석 기간');
  expect(html).toContain('정확한 시간 범위');
  expect(html).toContain('training-long-namespace');
  expect(html).toContain('2026. 10. 22. 하루 · 1일(24시간)');
  expect(html).toContain('dateTime="2026-10-23T07:33:35Z"');
  expect(html).toContain('자동 생성');
  expect(html).toContain('부분 산출');
  expect(html).toContain('계산 결과 요약');
  expect(html).toContain('저장 원문: 활동률 25.7%');
  expect(html).not.toContain('AI 해석 요약');
  expect(html).toContain('분석 대상 미확인');
  expect(html).toContain('생성 방식 미확인');
  expect(html).toContain('결과 미발행');
  expect(html).toContain('/reports/old');
  expect(JSON.stringify(items)).toBe(saved);
  expect(state.paths).toEqual([]);
});

it('uses the same scoped report request and date validation in both console layouts', () => {
  const path =
    '/reports?status=succeeded&topic=namespace_usage&analysis_from=2026-10-22&analysis_to=2026-10-22&received_from=2026-10-23&received_to=2026-10-24';
  render(<OperatorConsole />, path);
  const classicPath = state.paths.at(-1);
  const html = render(<OperatorConsole compact />, path);
  expect(state.paths.at(-1)).toBe(classicPath);
  const query = new URL(state.paths.at(-1)!, 'http://fixture').searchParams;
  expect(Object.fromEntries(query)).toMatchObject({
    limit: '30',
    status: 'succeeded',
    topic_id: 'namespace_usage',
    analysis_from: '2026-10-21T15:00:00.000Z',
    analysis_to: '2026-10-22T15:00:00.000Z',
    from: '2026-10-22T15:00:00.000Z',
    to: '2026-10-24T15:00:00.000Z',
  });
  expect(JSON.parse(query.get('scope')!)).toEqual({
    clusters: [{ cluster_id: 'c1', namespaces: null }],
  });
  expect(html).toContain('불러온 0건');
  expect(html).toContain('조회된 보고서가 없습니다.');
  expect(html).toContain('추가 필터');
  expect(html).toContain('href="/schedules"');
  expect(html).toContain('href="/reports/new"');
  expect(html.indexOf('<h1')).toBeLessThan(html.indexOf('aria-label="하위 메뉴"'));
  state.paths = [];
  render(<OperatorConsole compact />, '/reports?analysis_from=2026-10-24&analysis_to=2026-10-22');
  expect(state.paths).toEqual([]);
  state.error = true;
  const error = render(<OperatorConsole compact />, '/reports?status=failed');
  expect(error).not.toContain('불러온 0건');
  expect(error).toContain('fixture network error');
  expect(error).toContain('모든 조건 해제');
});
